"""E043 — the probe readout's synthetic self-check: a seeded 2400 dpi scan with planted edges, screens, cross-talk.

The pattern is measure/e041_probe_synth.py's and e041_scale_synth.py's (a 600 dpi page raster mapped through a
pose by nearest dot, Gaussian blur, seeded noise, row strip by row strip into one uint8 image).  The page is the
manifest's: the emitter's (--manifest, --gt) or, when absent, one this module builds to the frozen schema from
CMY-PROBE-M281 §2 (five c2 bands of one seeded four-state field, the eleven sweep ladders, the registry values
in five constructs, four white, two scrambled and one screened control, A4 at 600 dpi, the five fiducials of
experiments/041-m281-screen-routes/pclxl_probe.py:119-120).

Painted (scanned colours, not device RGB): paper (231, 232, 234); C (46, 151, 194), M (215, 67, 119),
Y (229, 219, 88) — the spec's measured bar colours; fiducials near-black.  PLANTED, per sweep ladder (seeded):
a plateau [lower, upper] strictly inside the ladder; bars on it are solid toner whose two foreign channels
darken linearly along the plateau (0 at the lower edge, `slope` at the upper; slope per ladder in
SLOPE_RANGE), bars off it carry a screen: a 2-D lattice at one of e041's lattices (two cosines at the lattice's
first two angles, frequency in page dots) of amplitude SCREEN_AMP x the local ink contrast (paper - ink).
The screened control carries a screen too; registry bars are solid toner; white bars paper; scrambled bars
their GT dot pattern in their toner.  The bands are their GT cells, no registration error planted.  Pose: tilt
ROT_DEG (<= 0.3 deg), scale 1.004, a shift, Gaussian blur BLUR_PX, noise NOISE_SD (seeded per strip).

Then the readout (measure/cmy_probe/readout.run) reads the TIFF and the self-check asserts: every planted edge
recovered within one ladder step, every midpoint within one step (edges from the stipple verdict's clean
bars; a ladder of fewer than five values is painted solid and not planted), the cross-talk ranking (Spearman
over every plateau bar of every ladder, measured vs planted, and per ladder), the screened control's legacy
score above 18 with the white / scrambled floor below it, the stipple verdict discriminating (white bars at
or below the clean bar, the screened control above the marginal bar), every registry bar clean, every
band's cell error below 1 %, every band's lattice x-profile (measure/cmy_probe/profile.py) below 18 in every
slice (the bands are planted unscreened).  Exit status 1 on any failure.
--case sheet2: the sheet-2 stand-in with planted checkerboards (dot gain, plane offset, one yellow stipple)
and dot patches, measure/cmy_probe/synth_sheet2.py (its own asserts beside these).

    PYTHONPATH=src:. env/bin/python -m measure.cmy_probe.synth --out <dir> [--seed 7] [--remove-scan]
    PYTHONPATH=src:. env/bin/python -m measure.cmy_probe.synth --case sheet2 --out <dir> --remove-scan
    PYTHONPATH=src:. env/bin/python -m measure.cmy_probe.synth --out <dir> \\
        --manifest build/e043/E043-m281-cmy-probe.manifest.json --gt build/e043/E043-m281-cmy-probe-gt.npz
An A4 page at 2400 dpi is a ~1.9 GB TIFF (written uncompressed via PIL; --remove-scan deletes it after the
readout); painting plus readout take a few minutes and ~8 GB.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.stats import spearmanr

from measure.cmy_probe.bars import AXIS_CHANNELS, TONER_CHANNEL, ladders, swept_value
from measure.cmy_probe.readout import run as run_readout
from measure.e041_scale_readout import LATTICES, UNSCREENED_MAX

Image.MAX_IMAGE_PIXELS = None
DPI = 600
SCAN_DPI = 2400
TAG = "E043-m281-cmy-probe"
PAGE_DOTS_XY = (4960, 7016)
LOOKUP = {"W": [255, 255, 255], "C": [0, 208, 255], "M": [240, 0, 192], "Y": [255, 255, 0]}
PAPER = (231.0, 232.0, 234.0)
TONER_SCAN = {"C": (46.0, 151.0, 194.0), "M": (215.0, 67.0, 119.0), "Y": (229.0, 219.0, 88.0)}
FID_SCAN = (28.0, 28.0, 30.0)
# experiments/041-m281-screen-routes/pclxl_probe.py:119-120: id, x, y, w, h (mm)
FIDUCIALS_MM = (("F0", 8.0, 8.0, 3.0, 3.0), ("F1", 199.0, 8.0, 3.0, 3.0), ("F2", 8.0, 286.0, 3.0, 3.0),
                ("F3", 199.0, 286.0, 3.0, 3.0), ("F4", 8.0, 12.0, 3.0, 6.0))
BAND_ARMS = ("M-hex", "M-a85", "I-2", "I-8", "I-ref")
CONSTRUCTS = ("mask-hex", "mask-a85", "I-2", "I-8", "I-ref")
BAND_X, BAND_Y0, BAND_W, BAND_H, BAND_GAP, CELL_DOTS = 283, 283, 4392, 432, 24, 2
BAR_W, BAR_H, BAR_PITCH_X, BAR_PITCH_Y, BARS_PER_ROW = 192, 48, 221, 72, 20
# CMY-PROBE-M281 §2's table: toner, axis, first, last, step, fixed components, append the span end
LADDER_SPECS: tuple[tuple[str, str, int, int, int, dict[str, int], bool], ...] = (
    ("C", "G", 160, 236, 2, {"R": 0, "B": 255}, False), ("C", "B", 192, 255, 4, {"R": 0, "G": 200}, True),
    ("C", "R", 0, 32, 4, {"G": 200, "B": 255}, False),
    ("M", "R", 220, 255, 2, {"B": 192, "G": 0}, False), ("M", "B", 150, 230, 2, {"R": 240, "G": 0}, False),
    ("M", "B", 150, 230, 4, {"R": 255, "G": 0}, False), ("M", "G", 0, 32, 4, {"R": 240, "B": 192}, False),
    ("Y", "RG", 200, 255, 4, {"B": 0}, False), ("Y", "B", 0, 48, 4, {"R": 255, "G": 255}, False),
    ("Y", "G", 192, 255, 4, {"R": 255, "B": 0}, False), ("Y", "R", 192, 255, 4, {"G": 255, "B": 0}, False))
SCREEN_AMP = 0.40
SLOPE_RANGE = (8.0, 40.0)
ROT_DEG, SCALE, SHIFT_MM, PAD_MM = 0.25, 1.004, (2.3, -1.7), 8.0
BLUR_PX, NOISE_SD = 1.2, 4.0
SPEARMAN_MIN = 0.9
CELL_ERR_MAX = 0.01


def mm_dots(mm: float) -> int:
    return int(math.floor(mm * DPI / 25.4 + 0.5))


# ---------------------------------------------------------------- the stand-in manifest (schema of record)

def ladder_bars(spec: tuple[str, str, int, int, int, dict[str, int], bool]) -> list[dict[str, Any]]:
    toner, axis, first, last, step, fixed, with_end = spec
    vals = list(range(first, last + 1, step)) + ([last] if with_end and (last - first) % step else [])
    out = []
    for v in vals:
        rgb = [fixed.get(ch, 0) for ch in "RGB"]
        for c in AXIS_CHANNELS[axis]:
            rgb[c] = v
        out.append({"kind": "sweep", "toner": toner, "axis": axis, "rgb": rgb, "construct": "mask-hex"})
    return out


def build_manifest(seed_cells: int = 43, seed_layout: int = 44) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """A manifest + GT to the frozen schema, for when the emitter's file is absent."""
    rows, cols = BAND_H // CELL_DOTS, BAND_W // CELL_DOTS
    states = np.array([0, 1, 2, 4], np.uint8)[np.random.default_rng(seed_cells).integers(0, 4, size=(rows, cols))]
    gt: dict[str, np.ndarray] = {"states": states}
    bands = [{"name": f"B{i + 1}", "arm": arm, "x_dots": BAND_X, "y_dots": BAND_Y0 + i * (BAND_H + BAND_GAP),
              "w_dots": BAND_W, "h_dots": BAND_H, "cell_dots": CELL_DOTS, "rows": rows, "cols": cols,
              "gt_key": "states"} for i, arm in enumerate(BAND_ARMS)]
    bars = [b for spec in LADDER_SPECS for b in ladder_bars(spec)]
    bars += [{"kind": "registry", "toner": t, "axis": None, "rgb": list(LOOKUP[t]), "construct": c}
             for t in "CMY" for c in CONSTRUCTS]
    bars += [{"kind": "white", "toner": None, "axis": None, "rgb": [255, 255, 255], "construct": "none"}
             for _ in range(4)]
    bars += [{"kind": "scrambled", "toner": t, "axis": None, "rgb": list(LOOKUP[t]), "construct": "none"}
             for t in ("C", "M")]
    bars += [{"kind": "screened", "toner": "C", "axis": None, "rgb": [128, 232, 255], "construct": "I-8"}]
    y0 = bands[-1]["y_dots"] + BAND_H + BAR_PITCH_Y - BAR_H
    order = np.random.default_rng(seed_layout).permutation(len(bars))
    for slot, i in enumerate(order):
        b = bars[int(i)]
        b.update(id=f"P{int(i):03d}", x_dots=BAND_X + (slot % BARS_PER_ROW) * BAR_PITCH_X,
                 y_dots=y0 + (slot // BARS_PER_ROW) * BAR_PITCH_Y, w_dots=BAR_W, h_dots=BAR_H, gt_key=None)
        if b["kind"] == "scrambled":
            b["gt_key"] = f"scrambled_{b['id']}"
            gt[b["gt_key"]] = np.random.default_rng([seed_layout, int(i)]).integers(0, 2, (BAR_H, BAR_W), dtype=np.uint8)
    fids = [{"id": f, "x_mm": x, "y_mm": y, "w_mm": w, "h_mm": h, "x_dots": mm_dots(x), "y_dots": mm_dots(y),
             "w_dots": mm_dots(w), "h_dots": mm_dots(h)} for f, x, y, w, h in FIDUCIALS_MM]
    man = {"tag": TAG, "dpi": DPI, "page_dots_xy": list(PAGE_DOTS_XY), "seed_cells": seed_cells,
           "seed_layout": seed_layout, "lookup": LOOKUP, "fiducials": fids, "bands": bands, "bars": bars,
           "job": {"file": "synthetic (measure/cmy_probe/synth.py)", "sha256": "", "bytes": 0}}
    return man, gt


# ---------------------------------------------------------------- planting

@dataclass
class Plant:
    """The planted truth: per ladder (toner, key) its plateau, lattice and slope; per bar colour and screen."""
    ladders: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    colour: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    screen: dict[str, str] = field(default_factory=dict)
    crosstalk: dict[str, float] = field(default_factory=dict)


def toner_of(bar: dict[str, Any]) -> str:
    return bar["toner"] if bar.get("toner") in TONER_SCAN else "C"


def foreign_mean(rgb: tuple[float, float, float], toner: str) -> float:
    return float(np.mean([rgb[c] for c in range(3) if c != TONER_CHANNEL[toner]]))


def plant(man: dict[str, Any], seed: int) -> Plant:
    """Seeded plateaus (strictly inside every ladder), lattices and cross-talk slopes; every bar's paint."""
    rng = np.random.default_rng([seed, 43043])
    p = Plant()
    names = list(LATTICES)
    for toner, ls in ladders(man["bars"]).items():
        for key, rows in ls.items():
            n = len(rows)
            if n < 5:                     # no plateau strictly inside with screened ends: painted solid, not planted
                continue
            k1 = int(rng.integers(1, max(2, n // 3 + 1)))
            k2 = int(rng.integers(max(k1 + 2, (2 * n) // 3), n - 1))
            vals = [swept_value(b) for b in rows]
            L = {"lower": vals[k1], "upper": vals[k2], "lattice": names[int(rng.integers(0, len(names)))],
                 "slope": float(rng.uniform(*SLOPE_RANGE)), "step": int(np.median(np.diff(vals)))}
            L["midpoint"] = int(math.floor(0.5 * (L["lower"] + L["upper"]) + 0.5))
            p.ladders[(toner, key)] = L
            base = TONER_SCAN[toner]
            for i, b in enumerate(rows):
                if k1 <= i <= k2:
                    t = (vals[i] - vals[k1]) / (vals[k2] - vals[k1])
                    col = tuple(base[c] - (L["slope"] * t if c != TONER_CHANNEL[toner] else 0.0) for c in range(3))
                    p.colour[b["id"]] = col
                    p.crosstalk[b["id"]] = foreign_mean(PAPER, toner) - foreign_mean(col, toner)
                else:
                    p.colour[b["id"]], p.screen[b["id"]] = base, L["lattice"]
    for b in man["bars"]:
        if b["id"] in p.colour:
            continue
        if b["kind"] in ("registry", "scrambled", "screened", "sweep") and b.get("toner"):
            p.colour[b["id"]] = TONER_SCAN[toner_of(b)]
        else:
            p.colour[b["id"]] = PAPER
        if b["kind"] == "screened":
            p.screen[b["id"]] = names[0]
    return p


def page_raster(man: dict[str, Any], gt: Any, p: Plant) -> tuple[np.ndarray, np.ndarray]:
    """(base (H, W, 3) float32 scanned colour per dot, screen (H, W) uint8: 0 none, 1 + lattice index)."""
    W, H = (int(v) for v in man["page_dots_xy"])
    base = np.empty((H, W, 3), np.float32)
    base[:] = PAPER
    screen = np.zeros((H, W), np.uint8)
    for f in man["fiducials"]:
        base[f["y_dots"]:f["y_dots"] + f["h_dots"], f["x_dots"]:f["x_dots"] + f["w_dots"]] = FID_SCAN
    lut = np.zeros((8, 3), np.float32)
    lut[0], lut[1], lut[2], lut[4] = PAPER, TONER_SCAN["C"], TONER_SCAN["M"], TONER_SCAN["Y"]
    for b in man["bands"]:
        st = np.asarray(gt[b.get("gt_key", "states")])
        cd = int(b.get("cell_dots", 2))
        dots = np.kron(st, np.ones((cd, cd), np.uint8))
        base[b["y_dots"]:b["y_dots"] + dots.shape[0], b["x_dots"]:b["x_dots"] + dots.shape[1]] = lut[dots]
    names = list(LATTICES)
    for b in man["bars"]:
        x, y, w, h = (int(b[k]) for k in ("x_dots", "y_dots", "w_dots", "h_dots"))
        if b["kind"] == "scrambled" and b.get("gt_key") in gt:
            pat = np.asarray(gt[b["gt_key"]], bool)[:h, :w]
            base[y:y + h, x:x + w][pat] = p.colour[b["id"]]
        else:
            base[y:y + h, x:x + w] = p.colour[b["id"]]
        if b["id"] in p.screen:
            screen[y:y + h, x:x + w] = 1 + names.index(p.screen[b["id"]])
    return base, screen


Overlay = Callable[[np.ndarray, np.ndarray, np.ndarray], None]


def paint_scan(base: np.ndarray, screen: np.ndarray, seed: int, strip_rows: int = 256,
               overlay: Overlay | None = None) -> np.ndarray:
    """e041_scale_synth.paint_scan's pose (page dot (x, y) -> canvas = s R sub (x, y) + pad + shift, nearest dot
    per pixel centre) with one base layer and the planted screens evaluated in page-dot coordinates, then
    `overlay(X, Y, val)` (continuous page-dot coordinates per pixel; paints sub-dot structure in place,
    measure/cmy_probe/synth_sheet2.py), Gaussian blur (halo 4 sigma per strip) and seeded noise per strip."""
    Hd, Wd = base.shape[:2]
    sub = SCAN_DPI / DPI
    pad = int(round(PAD_MM * SCAN_DPI / 25.4))
    Hs, Ws = int(Hd * sub * SCALE) + 2 * pad, int(Wd * sub * SCALE) + 2 * pad
    th = np.radians(ROT_DEG)
    Ri = np.array([[np.cos(th), np.sin(th)], [-np.sin(th), np.cos(th)]]) / (SCALE * sub)
    off = np.array([pad + SHIFT_MM[0] * SCAN_DPI / 25.4, pad + SHIFT_MM[1] * SCAN_DPI / 25.4])
    o = Ri @ off
    waves = []
    for fr0, angles in LATTICES.values():
        f_dot = fr0 * sub                                    # cycles per page dot (the lattices at 2400 dpi)
        waves.append([(2 * np.pi * f_dot * np.cos(np.radians(a)), 2 * np.pi * f_dot * np.sin(np.radians(a)))
                      for a in angles[:2]])
    paper = np.array(PAPER, np.float32)
    halo = int(math.ceil(4 * BLUR_PX)) + 1
    out = np.empty((Hs, Ws, 3), np.uint8)
    cols = np.arange(Ws) + 0.5
    for i, r0 in enumerate(range(0, Hs, strip_rows)):
        r1 = min(r0 + strip_rows, Hs)
        a0, a1 = max(0, r0 - halo), min(Hs, r1 + halo)
        C, R = np.meshgrid(cols, np.arange(a0, a1) + 0.5)
        X = Ri[0, 0] * C + Ri[0, 1] * R - o[0]
        Y = Ri[1, 0] * C + Ri[1, 1] * R - o[1]
        del C, R
        xd, yd = np.floor(X).astype(np.int64), np.floor(Y).astype(np.int64)
        ok = (xd >= 0) & (xd < Wd) & (yd >= 0) & (yd < Hd)
        val = np.empty(X.shape + (3,), np.float32)
        val[:] = paper
        val[ok] = base[yd[ok], xd[ok]]
        scr = np.zeros(X.shape, np.uint8)
        scr[ok] = screen[yd[ok], xd[ok]]
        for k, wv in enumerate(waves):
            m = scr == k + 1
            if m.any():
                s = 0.5 * sum(np.cos(kx * X[m] + ky * Y[m]) for kx, ky in wv)
                val[m] += SCREEN_AMP * (paper - val[m]) * s[:, None].astype(np.float32)
        if overlay is not None:
            overlay(X, Y, val)
        del X, Y, xd, yd, ok, scr
        for c in range(3):
            val[..., c] = ndimage.gaussian_filter(val[..., c], BLUR_PX, mode="nearest")
        blk = val[r0 - a0:r0 - a0 + (r1 - r0)]
        blk = blk + np.random.default_rng([seed, i]).standard_normal(blk.shape, np.float32) * NOISE_SD
        out[r0:r1] = np.clip(np.round(blk), 0, 255).astype(np.uint8)
    return out


# ---------------------------------------------------------------- the self-check

def check(summary: dict[str, Any], p: Plant) -> tuple[list[str], bool]:
    """The self-check table and whether every assertion holds."""
    r = summary["scans"][0]
    lines, ok_all = [], True
    lines.append(f"{'ladder':16s} {'step':>4s}  {'planted lo..hi->mid':>20s}  {'read lo..hi->mid':>20s}  "
                 f"{'lattice':>7s} {'xt rho':>6s}  ok")
    planted_xt, read_xt = [], []
    for (toner, key), L in sorted(p.ladders.items()):
        e = r["edges"].get(toner, {}).get("ladders", {}).get(key)
        if e is None or e["midpoint"] is None:
            lines.append(f"{toner} {key:14s} NOT READ")
            ok_all = False
            continue
        st = L["step"]
        ok = (abs(e["lower"] - L["lower"]) <= st and abs(e["upper"] - L["upper"]) <= st
              and abs(e["midpoint"] - L["midpoint"]) <= st)
        pl = [(p.crosstalk[q["id"]], q["crosstalk"]["mean"]) for q in e["plateau"] if q["id"] in p.crosstalk]
        rho = float(spearmanr(*zip(*pl))[0]) if len(pl) >= 3 else float("nan")
        ok &= not (np.isfinite(rho) and rho < SPEARMAN_MIN)
        planted_xt += [a for a, _ in pl]
        read_xt += [b for _, b in pl]
        ok_all &= ok
        lines.append(f"{toner} {key:14s} {st:4d}  {L['lower']:5d}..{L['upper']:3d} -> {L['midpoint']:3d}  "
                     f"{e['lower']:5d}..{e['upper']:3d} -> {e['midpoint']:3d}      {L['lattice']:>7s} "
                     f"{rho:6.3f}  {'ok' if ok else 'FAIL'}")
    rho_all = float(spearmanr(planted_xt, read_xt)[0]) if len(planted_xt) >= 3 else float("nan")
    ok = np.isfinite(rho_all) and rho_all >= SPEARMAN_MIN
    ok_all &= bool(ok)
    lines.append(f"cross-talk ranking over {len(planted_xt)} plateau bars: Spearman {rho_all:.4f} "
                 f"(>= {SPEARMAN_MIN}) {'ok' if ok else 'FAIL'}")
    fl = r["floor"]
    ok = bool(fl["screened"]) and fl["screened_ref"] > UNSCREENED_MAX and fl["floor_max"] < UNSCREENED_MAX
    ok_all &= ok
    lines.append(f"floor (white + scrambled) max {fl['floor_max']:.2f} < {UNSCREENED_MAX:g} < screened control "
                 f"{fl['screened_ref']:.2f}: {'ok' if ok else 'FAIL'}")
    for b in r["bands"]:
        ok = b["state_err"] < CELL_ERR_MAX and b["n_read"] == b["n_cells"]
        ok_all &= ok
        lines.append(f"band {b['name']} {str(b['arm']):6s} cell error {100 * b['state_err']:.4f} % "
                     f"({b['n_read']}/{b['n_cells']} read) < {100 * CELL_ERR_MAX:g} %: {'ok' if ok else 'FAIL'}")
        sc = np.asarray(b["profile_scores"], np.float64)
        ok = bool(len(sc)) and bool(np.isfinite(sc).all()) and bool((sc < UNSCREENED_MAX).all())
        c3 = int(b.get("cell_dots", 2)) != 2       # the legacy lattice score reads a c3 field's own anisotropy
        ok_all &= ok or c3
        lines.append(f"band {b['name']} {str(b['arm']):6s} lattice x-profile max {np.nanmax(sc):.2f} at x "
                     f"{b['profile_max_slice_x_mm']:.1f} mm over {len(sc)} slices < {UNSCREENED_MAX:g} in every "
                     f"slice: {'ok' if ok else ('a record (c3: legacy score not valid on a c3 field)' if c3 else 'FAIL')}")
    sf = r["stipple_floor"]
    ok = bool(sf["discriminating"]) and sf["white_max"] <= sf["clean_max"]
    ok_all &= ok
    lines.append(f"stipple verdict: white bars max {sf['white_max']:.1f} <= clean bar {sf['clean_max']:.1f}; screened "
                 f"control {min(sf['screened']) if sf['screened'] else float('nan'):.1f} > marginal bar "
                 f"{sf['marginal_max']:.1f}: {'ok' if ok else 'FAIL'}")
    regs = [b for b in summary["scans"][0]["bars"] if b["kind"] == "registry"]
    ok = all(b["verdict"] == "clean" for b in regs)
    ok_all &= ok
    lines.append(f"registry bars clean: {sum(b['verdict'] == 'clean' for b in regs)}/{len(regs)} "
                 f"{'ok' if ok else 'FAIL'}")
    return lines, bool(ok_all)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=None, help="the emitter's manifest (default: build a stand-in)")
    ap.add_argument("--gt", default=None, help="the emitter's GT npz (with --manifest)")
    ap.add_argument("--out", required=True, help="output directory (scan, stand-in manifest, readout/)")
    ap.add_argument("--seed", type=int, default=7, help="planting and noise seed")
    ap.add_argument("--remove-scan", action="store_true", help="delete the synthetic TIFF after the readout")
    ap.add_argument("--case", choices=("sheet1", "sheet2"), default="sheet1",
                    help="sheet2: a stand-in sheet-2 manifest with planted checkerboards and dots "
                         "(measure/cmy_probe/synth_sheet2.py)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.case == "sheet2":
        from measure.cmy_probe.synth_sheet2 import main_sheet2
        sys.exit(main_sheet2(out, a.seed, a.remove_scan))
    if a.manifest:
        if not a.gt:
            raise SystemExit("--manifest needs --gt")
        man_path, gt_path = Path(a.manifest), Path(a.gt)
        man = json.loads(man_path.read_text())
        gt: Any = np.load(gt_path)
    else:
        man, gt = build_manifest()
        man_path, gt_path = out / f"{TAG}.manifest.json", out / f"{TAG}-gt.npz"
        man_path.write_text(json.dumps(man, indent=1))
        np.savez_compressed(gt_path, **gt)
    p = plant(man, a.seed)
    base, screen = page_raster(man, gt, p)
    img = paint_scan(base, screen, a.seed)
    del base, screen
    scan_path = out / f"{man['tag']}-synth-{a.seed}.tiff"
    Image.fromarray(img).save(scan_path, dpi=(SCAN_DPI, SCAN_DPI))
    print(f"wrote {scan_path} {img.shape[1]} x {img.shape[0]} px; {len(p.ladders)} ladders planted")
    del img
    try:
        summary = run_readout([scan_path], man_path, gt_path, out / "readout", float(SCAN_DPI))
    finally:
        if a.remove_scan:
            scan_path.unlink(missing_ok=True)
    lines, ok = check(summary, p)
    print("\nSELF-CHECK (planted vs read)\n" + "\n".join(lines) + f"\nSELF-CHECK {'PASSED' if ok else 'FAILED'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

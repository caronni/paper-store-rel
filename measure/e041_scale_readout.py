"""e041 S14 — read the PAGE-SCALE probe: do alphabets that read cleanly in 3.9 mm patches survive a page?

The S14 sheet (tag "S14-ps-scale", the contract in the e041 log) covers ~85 % of an A4 page with full-width
noise bands (x 12 .. ~198 mm, crossing the engine's stripe at 98-118 mm): per band one alphabet (cmy4-solid
{W,C,M,Y}, cmy8-engine {W,C,M,Y,CM,CY,MY,CMY}, cmyk5 {W,C,M,Y,K}), one cell size (c3 / c2), one halftone
method (smooth / detail), one neutral axis (process / toner), ColorSmart matching at the device default
(section A) or off (section B), one image or 24 abutting tile images (B2); plus two strips of solid bars.
The generator writes the manifest (bands, bars, and the readout WINDOWS: each data band tiled into 31 x 31
c3 cells = 93 dots, or 46 x 46 c2 cells = 92 dots, whole windows only) and <tag>-bands.npz with per data band
"states_<band>" (cell grid, an index into the band's alphabet) and "planes_<band>" (4 x H x W, C/M/Y/K ink
per dot).  This instrument works from that npz and never regenerates a raster.

On an RGB scan at --scan-dpi (default 2400; 4800 for S17), either orientation on the glass.  Every scan-px
quantity scales with sub = scan dpi / 600 px per dot (4 at 2400, 8 at 4800): the rectified frame, the OR-ed
search (SEARCH_MM, in mm), the per-plane search (3 dots = 12 / 24 px), the cell boxes (half a cell / the whole
cell), the bars' lattice windows (LAT_WIN_PX at 2400 = 1.016 mm) and their lattice frequencies (cycles per px
x 2400 / scan dpi), the fiducial finder's block factor and its px tolerances (e041_probe_readout); pose
offsets in the CSVs stay in scan px of the given dpi.  At 2400 every output is byte-identical to the readout
before the dpi axis.  A 4800 dpi A4 scan is held once as uint8 (~6.9 GB, read by tifffile when the TIFF is
uncompressed or losslessly compressed, else by PIL, which peaks at ~3.7x the image while decoding):

1. page fit: the five fiducials (measure.e041_probe_readout.fit_page, imported);
2. per WINDOW: its states and dot planes sliced from the band arrays; the window plus SEARCH_MM (0.5 mm)
   and the per-plane search radius on every side resampled page-aligned at 4 px per dot; the template =
   the window's OWN dot-level ink mask (all planes OR-ed, no white frame: the field around it is noise of
   the same band, independent of the window's own cells, so the correlation peak is the window's alone —
   but the search must stay well inside a window, a neighbour's content being independent, not absent),
   registered against darkness = 255 - min(R, G, B)
   by FFT cross-correlation within +/- SEARCH_MM (e041_gt_compare.xcorr_shift); below REG_MIN_PEAK the
   nominal position is kept (reg_ok 0); an integer peak on the search boundary sets reg_edge (the window
   may lie beyond the search, or the peak is a neighbour's); then a pose PER PLANE within +/- 12 px of
   the OR-ed one (e041_mixture_readout.plane_poses: own mask vs own spectrally unmixed coverage; 041.5f)
   and per cell the mean R, G, B over a centre box of half the cell, R at C's pose, G at M's, B at Y's
   (e041_mixture_readout.sample_per_plane; a K-carrying state scored at K's pose for the channels whose
   plane it lacks: hypothesis_features); the single-OR-ed-pose reading is kept as *_singlepose;
   the WHOLE-CELL mean at the same per-plane poses is kept as *_wholecell (S16: composite cells put their
   levels at the cell's edges, outside the cell_px/2 core box — the dot-mixed overlaps, the 3/6/9-dot
   amplitude states; for solid cells it is the same reading with more paper in the box);
3. STATE error, the figure of merit: a nearest-mean classifier in RGB over the band's alphabet
   (e041_mixture_readout.class_means / classify): "loo" = means fitted on the window itself, leave-one-out;
   "cross" = means fitted on the up-to-8 neighbouring windows of the same band (never the window);
   "band" = one set of means fitted on every window of the band (the window's own 1/N share included) —
   the channel a receiver with one colour table per band would see;
   loo has a construction floor: a state with ONE cell in a window has no leave-one-out mean (own-class
   distance inf, e041_mixture_readout.classify) and reads wrong whatever the channel (the S16 synthetic:
   8 such cells, T4 4 / T6 4, and they are every loo error; cross and band 0).  A window with no plane
   between PLANE_MIN_INK and PLANE_MAX_INK (all white) is skipped only because plane_poses stacks no plane
   and numpy raises ValueError, which the window loop prints as "skipped": there is no explicit no-ink
   guard (S16: T13's 16 all-white windows; the skipped set equals the all-W set, ps_trigger_verify);
3b. LAYOUT (S17; bands whose "layout_catalogue" gives some state more than one dot arrangement, with
   "layouts_<band>" in the npz): every such cell's layout decided GIVEN ITS TRUE STATE, without the truth —
   poses from the window's single-candidate (solid) cells only, a density forward model fitted on those cells,
   each candidate's patch rendered at the planes' own poses, normalised correlation, argmax
   (measure.e041_layout_readout, its docstring has the method); scored as layout / orientation / phase error
   per window and band, per state confusion + MI, and combined bits per cell = state MI + layout MI x the
   state's share of cells (also per mm^2).  Bands without a layout axis print nothing new;
4. per PLANE (C -> R, M -> G, Y -> B, K -> max(R, G, B); C/M/Y leave out cells with K ink): d', hard error at
   the midpoint and at the best single threshold (e041_mixture_readout.plane_stats);
5. per BAND: mean / median / p90 of the window state errors, per-plane errors (window means), the pooled
   confusion matrix (loo) and its empirical mutual information in bits per cell, with the raw density
   log2|alphabet| bits per cell -> bits per mm^2 beside it; two profiles: state error vs window column
   (x, crossing the stripe) and vs window row (y, the process direction);
6. per strip BAR: mean RGB over the interior eroded BAR_ERODE_MM, and the screen-lattice score: in
   LAT_WIN_PX (96 px) raw-scan windows tiled over that interior, on the mean of the bar's own channel(s)
   (rgb < 128; all three when none), the power at each known engine lattice (165 lpi +-14.2 deg, 188 lpi
   +-71 / +-19 deg, 212 lpi +-45 deg, frequency AND angle) over the median power on that lattice's frequency
   ring; per lattice the mean over windows; score = the largest lattice mean.  Floor: <= UNSCREENED_MAX
   (~18, the S10p2 calibration: scrambled 5.9, white paper 19) reads unscreened.  Checked against the
   record: on the S12 scan this scorer reproduces e041/mixture/S11-S12-bar-screen.json (the S12 bars,
   whose 24-dot height is one window) at Spearman 0.93 over 258 bars, medians 0.90-0.98x the recorded scores.

Figures of merit: per band state_err loo / cross / band (mean over windows), per-plane hard_err_best, MI
bits per cell and per mm^2; per bar the lattice score and mean RGB.  The report prints per band one line,
then the comparisons A1 vs B1 (matching), B1 vs B2 (one image vs 24 tiles), A3 vs B4 (cmyk5 matching),
B1 vs B3 (c3 Smooth vs c2 Detail: two fields differ), A2 alone (cmy8 at page scale), with --patch-ref the
S12 patch-level number for the same construction beside each band (REF_ARMS: A09, A12, A14, A17 only),
the plane offsets vs C by x, the bar table per section, and the MATCHING WITNESS: the pure-cyan
(0, 255, 255) bars of strip A (matching default) vs strip B (matching off) — A screened / B solid = the
per-object matching control works; both solid = a page-global latch; both screened = no per-image effect —
and the strip-B M-solid verdict.
Outputs in --out: <tag>-windows.csv, <tag>-bands.csv, <tag>-bars.csv, <tag>-summary.json and
<tag>-map-<band>.png (window loo state error per band; white 0, yellow, red, black at the scale printed).
The layout columns are appended at the END of the window CSV (layout_err, orient_err, phase_err,
n_layout_cells) and the band CSV (... mi_layout_bits_per_cell, combined_bits_per_cell, combined_bits_per_mm2),
empty for bands without a layout axis; the report adds a layout line per such band and a per-x profile of the
window orientation error.

    PYTHONPATH=src:. env/bin/python -m measure.e041_scale_readout \\
        --scan <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S14/captures/S14-canon-2400rgb.tiff \\
        --manifest <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S14/jobs/S14-ps-scale.manifest.json \\
        --patch-ref build/e041/mixture/S12-ps-mixture-patches.csv \\
        --out build/e041/scale
    (--bands P overrides the npz path; default <manifest dir>/<tag>-bands.npz; --scan-dpi 4800 for a 4800
    dpi scan.)

Smoke test without printer or scanner: measure/e041_scale_synth.py paints the same contract.  On the S14
geometry (2867 windows, 42 bars) a run takes ~85 s and ~7 GB.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from measure.e041_gt_compare import xcorr_shift
from measure.e041_layout_readout import (Catalogue, band_layout, catalogue_of, check_catalogue,
                                         decide_window, layouts_of, mutual_info_bits, ring_states,
                                         window_scores)
from measure.e041_mixture_readout import (PLANES, cell_fractions, class_means, classify, hypothesis_features,
                                          plane_poses, plane_search_px, plane_stats, plane_values,
                                          pose_record, sample_per_plane, state_plane_sets, state_report)
from measure.e041_probe_readout import (SCAN_DPI_NOMINAL, SUB_PX_PER_DOT, Scan, cell_samples, fit_page,
                                        jsonable, page_white, sample_rect, sub_px_per_dot)

SEARCH_MM = 0.5                         # OR-ed search radius; a peak on its boundary is flagged (reg_edge)
REG_MIN_PEAK = 0.25
WINDOW_CELLS = {3: 31, 2: 46}
BAR_ERODE_MM = 0.3
LAT_WIN_PX = 96                         # bar lattice window at 2400 dpi (1.016 mm); x sub / 4 at any dpi
UNSCREENED_MAX = 18.0
LATTICES: dict[str, tuple[float, tuple[float, ...]]] = {   # name -> (cycles per scan px at 2400 dpi, deg);
    "165lpi": (0.0691, (14.2, -14.2)),
    "188lpi": (188.0 / 2400.0, (71.0, -71.0, 19.0, -19.0)),
    "212lpi": (0.0880, (45.0, -45.0)),                     # at another dpi x 2400 / scan dpi
}
REF_ARMS: dict[tuple[str, int], tuple[str, ...]] = {        # (alphabet family, cell dots) -> S12 arms,
    ("cmy4-solid", 3): ("A09",),                               # each the band's own construction: A09
    ("cmy4-solid", 2): ("A12",),                               # cmy4 c3 M-solid, A12 cmy4 c2 M-solid,
    ("cmyk5", 3): ("A14",),                                    # A14 cmyk5 c3, A17 cmy8 c3 engine
    ("cmy8-engine", 3): ("A17",),                              # (M-corner, S9's palette)
}
FAMILY_OF_STATES = {("W", "C", "M", "Y"): "cmy4-solid", ("W", "C", "M", "Y", "K"): "cmyk5",
                    ("W", "C", "M", "Y", "CM", "CY", "MY", "CMY"): "cmy8-engine"}
COMPARISONS = (("A1", "B1", "colour matching default vs off"), ("B1", "B2", "one image vs 24 tile images"),
               ("A3", "B4", "cmyk5: matching default vs off"), ("B1", "B3", "c3 Smooth vs c2 Detail"))
WITNESS_RGB = (0, 255, 255)                                 # the matching witness: the pure-cyan bars
BAR_ORDER = ("C", "M-solid", "M-corner", "Y", "K", "CM", "CY", "MY", "CMY")


# ---------------------------------------------------------------- manifest access

def dots(d: dict[str, Any], k: str, dpi: float) -> int:
    """A dot coordinate from k_dots, k or k_mm (the contract names 'x/y/w/h dots')."""
    for key in (f"{k}_dots", k):
        if key in d and isinstance(d[key], (int, float)):
            return int(round(d[key]))
    if f"{k}_mm" in d:
        return int(round(float(d[f"{k}_mm"]) * dpi / 25.4))
    raise SystemExit(f"manifest entry {d.get('id', d.get('name'))} lacks {k}")


def rect_dots(d: dict[str, Any], dpi: float) -> tuple[int, int, int, int]:
    return dots(d, "x", dpi), dots(d, "y", dpi), dots(d, "w", dpi), dots(d, "h", dpi)


def page_frame(man: dict[str, Any]) -> dict[str, Any]:
    """The fit_page / page_white view: page_mm and fiducials in mm, whatever unit the manifest used."""
    dpi = float(man["dpi"])
    if "page_mm" in man:
        page_mm = [float(v) for v in man["page_mm"]]
    else:
        pd = man.get("page_dots") or [man["page_w_dots"], man["page_h_dots"]]
        if isinstance(pd, dict):
            pd = [pd["w"], pd["h"]]
        page_mm = [float(v) * 25.4 / dpi for v in pd]
    fids = []
    for f in man["fiducials"]:
        x, y, w, h = rect_dots(f, dpi)
        fids.append({"id": f["id"], "x_mm": x * 25.4 / dpi, "y_mm": y * 25.4 / dpi,
                     "w_mm": w * 25.4 / dpi, "h_mm": h * 25.4 / dpi})
    return {"dpi": dpi, "page_mm": page_mm, "fiducials": fids}


def states_of(b: dict[str, Any]) -> list[str]:
    """The band's state names: "states" when "alphabet" names the family (the generator's form), else the
    alphabet list itself."""
    return list(b["states"]) if isinstance(b.get("alphabet"), str) else list(b["alphabet"])


def family_of(b: dict[str, Any]) -> str:
    if isinstance(b.get("alphabet"), str):
        return str(b["alphabet"])
    plain = tuple("M" if s.startswith("M-") else s for s in b["alphabet"])
    return FAMILY_OF_STATES.get(plain, "|".join(b["alphabet"]))


def band_arrays(npz: Any, b: dict[str, Any], dpi: float) -> tuple[np.ndarray, np.ndarray] | None:
    """(states, planes) of a data band, or None for a band with no arrays (a strip)."""
    for key in (b.get("band"), b.get("name")):
        if key is not None and f"states_{key}" in npz:
            states = np.asarray(npz[f"states_{key}"], np.uint8)
            planes = np.asarray(npz[f"planes_{key}"], np.uint8)
            break
    else:
        return None
    _, _, w, h = rect_dots(b, dpi)
    cd = int(b["cell_dots"])
    if planes.shape != (4, h, w) or states.shape != (h // cd, w // cd):
        raise SystemExit(f"band {b['name']}: states {states.shape} / planes {planes.shape} do not match "
                         f"{w} x {h} dots at c{cd} — contract fork")
    if int(states.max()) >= len(states_of(b)):
        raise SystemExit(f"band {b['name']}: state index outside its alphabet {states_of(b)}")
    return states, planes


def tile_windows(b: dict[str, Any], dpi: float) -> list[dict[str, Any]]:
    """The contract's tiling, used when the manifest carries no windows: whole windows from the top-left."""
    x, y, w, h = rect_dots(b, dpi)
    cd = int(b["cell_dots"])
    n = WINDOW_CELLS[cd] * cd
    return [{"id": f"{b['name']}-{r}-{c}", "band": b["band"], "x_dots": x + c * n, "y_dots": y + r * n,
             "cells": WINDOW_CELLS[cd], "cell_dots": cd, "tile": None}
            for r in range(h // n) for c in range(w // n)]


def band_of(bands: list[dict[str, Any]], key: Any) -> dict[str, Any]:
    for b in bands:
        if key in (b.get("band"), b.get("name")):
            return b
    raise SystemExit(f"window refers to band {key!r}, not in the manifest")


# ---------------------------------------------------------------- per window

def register(rect: np.ndarray, ink: np.ndarray, s_px: int, p_px: int) -> tuple[float, float, float, bool]:
    """(oy, ox, peak, edge): the window's top-left in rect px; rect = the window + s_px + p_px on every
    side, the OR-ed search spans +/- s_px around the nominal (the outer p_px is the per-plane search's
    room); edge = the integer peak on the search boundary."""
    dark = 255.0 - rect.min(axis=2)
    if p_px:
        dark = dark[p_px:-p_px, p_px:-p_px]
    dy, dx, peak = xcorr_shift(dark, ink, s_px)
    edge = min(dy, dx) < 0.5 or max(dy, dx) > 2 * s_px - 0.5
    return dy + p_px, dx + p_px, peak, edge


def read_window(scan: Scan, A: np.ndarray, w: dict[str, Any], b: dict[str, Any], states: np.ndarray,
                planes: np.ndarray, dpi: float, white: np.ndarray, sub: int = SUB_PX_PER_DOT,
                lay: tuple[Catalogue, np.ndarray] | None = None) -> dict[str, Any]:
    """One window at sub px per dot (scan dpi / print dpi); lay = the band's (catalogue, layouts) when the
    band has a layout axis: the layout decision (e041_layout_readout.decide_window) is added."""
    bx, by, _, _ = rect_dots(b, dpi)
    cd, cells = int(w["cell_dots"]), int(w["cells"])
    xd, yd = dots(w, "x", dpi), dots(w, "y", dpi)
    n_dots = cells * cd
    if (xd - bx) % cd or (yd - by) % cd:
        raise SystemExit(f"window {w['id']}: not on the band's cell grid — contract fork")
    r0, c0 = (yd - by) // cd, (xd - bx) // cd
    st = states[r0:r0 + cells, c0:c0 + cells]
    pl = planes[:, yd - by:yd - by + n_dots, xd - bx:xd - bx + n_dots]
    if st.shape != (cells, cells) or pl.shape[1:] != (n_dots, n_dots):
        raise SystemExit(f"window {w['id']}: outside its band — contract fork")
    dot_mm = 25.4 / dpi
    step = dot_mm / sub
    s_px = int(round(SEARCH_MM / step))
    p_px = plane_search_px(sub)
    m_px = s_px + p_px
    n_px = n_dots * sub
    x0, y0 = xd * dot_mm, yd * dot_mm
    k = np.arange(n_px + 2 * m_px)
    rect = sample_rect(scan, A, x0 + (k - m_px) * step, y0 + (k - m_px) * step)
    ink = np.kron(pl.max(axis=0).astype(np.float32), np.ones((sub,) * 2, np.float32))
    oy, ox, peak, reg_edge = register(rect, ink, s_px, p_px)
    reg_ok = bool(peak >= REG_MIN_PEAK)
    if not reg_ok:
        oy = ox = float(m_px)
    cell_px = cd * sub
    vals1 = cell_samples(rect, oy, ox, cells, cell_px)
    poses = plane_poses(rect, pl, oy, ox, white, p_px, sub)
    vals, vals_k = sample_per_plane(rect, poses, oy, ox, cells, cell_px)
    # the whole cell at the same poses: composite cells (S16 T10's 3/6/9-dot levels, the dot-mixed
    # overlaps) put their information at the cell's edges, where the cell_px/2 core box cannot see it
    vals_w, vals_wk = sample_per_plane(rect, poses, oy, ox, cells, cell_px, box=cell_px)
    frac = cell_fractions(pl, cells, cd)
    n_win = cells * cd
    row: dict[str, Any] = {"id": w["id"], "band": b["name"], "section": b.get("section"),
                           "matching": b.get("matching"), "tile": w.get("tile"),
                           "grid_row": (yd - by) // n_win, "grid_col": (xd - bx) // n_win,
                           "x_dots": xd, "y_dots": yd, "x_mm": x0, "y_mm": y0,
                           "xc_mm": x0 + 0.5 * n_dots * dot_mm, "yc_mm": y0 + 0.5 * n_dots * dot_mm,
                           "cells": cells, "cell_dots": cd, "reg_ok": reg_ok, "reg_edge": bool(reg_edge),
                           "reg_peak": float(peak), "reg_dy_mm": (oy - m_px) * step,
                           "reg_dx_mm": (ox - m_px) * step}
    no_k = frac[3] <= 1e-9
    every = np.ones_like(no_k)
    row["planes"] = {PLANES[i]: plane_stats(plane_values(vals_k if i == 3 else vals, i), frac[i],
                                            every if i == 3 else no_k) for i in range(4)}
    row["planes_singlepose"] = {PLANES[i]: plane_stats(plane_values(vals1, i), frac[i],
                                                       every if i == 3 else no_k) for i in range(4)}
    row["poses"] = pose_record(poses, oy, ox)
    y = st.reshape(-1).astype(np.int64)
    sets = state_plane_sets(frac, y, len(states_of(b)))
    row["_X"] = hypothesis_features(vals.reshape(-1, 3).astype(np.float64),
                                    vals_k.reshape(-1, 3).astype(np.float64), sets)
    row["_XW"] = hypothesis_features(vals_w.reshape(-1, 3).astype(np.float64),
                                     vals_wk.reshape(-1, 3).astype(np.float64), sets)
    row["_X1"] = vals1.reshape(-1, 3).astype(np.float64)
    row["_y"] = y
    if lay is not None:
        try:
            dec, row["layout_info"] = decide_window(rect, ring_states(states, r0, c0, cells), lay[0], sub,
                                                    s_px, p_px, white, (float(m_px), float(m_px)))
            row.update(window_scores(lay[0], st, lay[1][r0:r0 + cells, c0:c0 + cells], dec))
        except ValueError as exc:                           # the state reading stands without the layout
            print(f"  window {w['id']}: layout skipped ({exc})")
    return row


def classify_windows(rows: list[dict[str, Any]], alphabets: dict[str, list[str]]) -> None:
    """Per-plane-sampled RGB (_X) -> state_{loo,cross,band}; the single OR-ed pose (_X1) -> the same with
    the suffix _singlepose; the whole-cell mean at the per-plane poses (_XW) -> the suffix _wholecell."""
    by_band: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_band[r["band"]].append(r)
    for name, rs in by_band.items():
        alpha = alphabets[name]
        S = len(alpha)
        grid = {(r["grid_row"], r["grid_col"]): r for r in rs}
        for xkey, sfx in (("_X", ""), ("_X1", "_singlepose"), ("_XW", "_wholecell")):
            mu_b, _ = class_means(np.concatenate([r[xkey] for r in rs]),
                                  np.concatenate([r["_y"] for r in rs]), S)
            for r in rs:
                X, y = r[xkey], r["_y"]
                mu, n = class_means(X, y, S)
                r[f"state_loo{sfx}"] = state_report(y, classify(X, y, mu, n), alpha)
                r[f"state_band{sfx}"] = state_report(y, classify(X, y, mu_b, None), alpha)
                nb = [grid[(r["grid_row"] + dr, r["grid_col"] + dc)] for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                      if (dr or dc) and (r["grid_row"] + dr, r["grid_col"] + dc) in grid]
                if nb:
                    mu_x, _ = class_means(np.concatenate([o[xkey] for o in nb]),
                                          np.concatenate([o["_y"] for o in nb]), S)
                    r[f"state_cross{sfx}"] = state_report(y, classify(X, y, mu_x, None), alpha)
                else:
                    r[f"state_cross{sfx}"] = None
                r["n_neighbours"] = len(nb)
                r[f"state_means{sfx}"] = {s: mu[i].tolist() for i, s in enumerate(alpha)}
                for k in ("loo", "cross", "band"):
                    rep = r[f"state_{k}{sfx}"]
                    r[f"state_err_{k}{sfx}"] = rep["err"] if rep else float("nan")


# ---------------------------------------------------------------- per band

def nanstat(v: list[float], f: Any) -> float:
    a = np.array([x for x in v if x is not None and np.isfinite(x)], np.float64)
    return float(f(a)) if a.size else float("nan")


def band_summary(b: dict[str, Any], rs: list[dict[str, Any]], dpi: float,
                 cat: Catalogue | None = None) -> dict[str, Any]:
    alpha = states_of(b)
    cd = int(b["cell_dots"])
    out: dict[str, Any] = {"name": b["name"], "band": b.get("band"), "section": b.get("section"),
                           "matching": b.get("matching"), "family": family_of(b), "alphabet": alpha,
                           "cell_dots": cd,
                           "method": b.get("method"), "neutral": b.get("neutral"),
                           "objects": len(b.get("images") or [None]), "seed": b.get("seed"),
                           "windows": len(rs), "reg_nominal": sum(1 for r in rs if not r["reg_ok"]),
                           "reg_edge": sum(1 for r in rs if r["reg_edge"]),
                           "reg_shift_max_mm": max((abs(r["reg_dx_mm"]) + abs(r["reg_dy_mm"]) for r in rs),
                                                   default=float("nan"))}
    for k in ("loo", "cross", "band"):
        for sfx in ("", "_singlepose", "_wholecell"):
            v = [r[f"state_err_{k}{sfx}"] for r in rs]
            out[f"state_err_{k}{sfx}"] = {"mean": nanstat(v, np.mean), "median": nanstat(v, np.median),
                                          "p90": nanstat(v, lambda a: np.quantile(a, 0.9)),
                                          "max": nanstat(v, np.max)}
    out["pose"] = {pl: {"flags": {f: sum(1 for r in rs if r["poses"][pl]["flag"] == f)
                                  for f in ("ok", "edge", "weak", "collinear", "absent")},
                        "dy_vs_C_median": nanstat([r["poses"][pl]["dy_vs_C_px"] for r in rs], np.median),
                        "dx_vs_C_median": nanstat([r["poses"][pl]["dx_vs_C_px"] for r in rs], np.median)}
                   for pl in PLANES}
    out["plane"] = {pl: {m: nanstat([r["planes"][pl][m] for r in rs], np.mean)
                         for m in ("hard_err", "hard_err_best", "dprime")} for pl in PLANES}
    conf = {k: np.sum([r[f"state_{k}"]["confusion"] for r in rs if r[f"state_{k}"]], axis=0)
            for k in ("loo", "band", "band_wholecell")}
    cells_per_mm2 = (dpi / 25.4 / cd) ** 2
    out["density"] = {"cells_per_mm2": cells_per_mm2, "raw_bits_per_cell": math.log2(len(alpha)),
                      "raw_bits_per_mm2": cells_per_mm2 * math.log2(len(alpha))}
    for k, c in conf.items():
        mi = mutual_info_bits(np.asarray(c, np.float64))
        out["density"][f"mi_{k}_bits_per_cell"] = mi
        out["density"][f"mi_{k}_bits_per_mm2"] = mi * cells_per_mm2
        out[f"confusion_{k}"] = np.asarray(c).tolist()
    for axis, key, centre in (("col", "grid_col", "xc_mm"), ("row", "grid_row", "yc_mm")):
        groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for r in rs:
            groups[r[key]].append(r)
        out[f"profile_{axis}"] = [{"index": i, "mm": float(np.mean([r[centre] for r in groups[i]])),
                                   "n": len(groups[i]),
                                   "state_err_loo": nanstat([r["state_err_loo"] for r in groups[i]], np.mean),
                                   "state_err_band": nanstat([r["state_err_band"] for r in groups[i]],
                                                             np.mean),
                                   "state_err_loo_singlepose": nanstat(
                                       [r["state_err_loo_singlepose"] for r in groups[i]], np.mean),
                                   **{f"{pl}_d{a}_vs_C_px": nanstat(
                                       [r["poses"][pl][f"d{a}_vs_C_px"] for r in groups[i]], np.median)
                                      for pl in "MYK" for a in "yx"},
                                   **({k: nanstat([r.get(k, np.nan) for r in groups[i]], np.mean)
                                       for k in ("layout_err", "orient_err", "phase_err")}
                                      if cat is not None else {})}
                                  for i in sorted(groups)]
    if cat is not None and any("_lay" in r for r in rs):
        d = out["density"]
        out["layout"] = band_layout(cat, rs, {"band": d["mi_band_bits_per_cell"],
                                              "band_wholecell": d["mi_band_wholecell_bits_per_cell"]},
                                    cells_per_mm2)
    return out


def patch_reference(path: Path | None, b: dict[str, Any]) -> dict[str, Any] | None:
    """The S12 patch-level figures for the band's alphabet / cell / method (uniform fraction)."""
    if path is None:
        return None
    arms = REF_ARMS.get((family_of(b), int(b["cell_dots"])))
    if not arms:
        return None
    with open(path, newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["arm"] in arms and r["fraction"] == "uniform"
                and r["method"] == b.get("method")]
    if not rows:
        return None

    def mean(col: str) -> float:
        return nanstat([float(r[col]) if r.get(col) else float("nan") for r in rows], np.mean)
    return {"arms": list(arms), "n_patches": len(rows), "state_err_loo": mean("state_err_loo"),
            "state_err_cross": mean("state_err_cross"),
            "state_err_loo_singlepose": mean("state_err_loo_singlepose"),
            "plane_hard_err_best": {pl: mean(f"{pl}_hard_err_best") for pl in PLANES}}


# ---------------------------------------------------------------- bars

def own_channels(rgb: list[int]) -> tuple[int, ...]:
    own = tuple(c for c in range(3) if rgb[c] < 128)
    return own or (0, 1, 2)


def lattice_ratios(g: np.ndarray, cyc_scale: float = 1.0) -> dict[str, float]:
    """Per known lattice: max power at its (frequency, angle) points over the median on its ring; the
    LATTICES frequencies (cycles per px at 2400 dpi) x cyc_scale (2400 / scan dpi)."""
    g = g.astype(np.float64) - g.mean()
    n = g.shape[0]
    S = np.abs(np.fft.fftshift(np.fft.fft2(g * np.outer(np.hanning(n), np.hanning(n))))) ** 2
    f = np.fft.fftshift(np.fft.fftfreq(n))
    FR = np.hypot(f[:, None], f[None, :])
    out = {}
    for name, (fr0, angles) in LATTICES.items():
        fr = fr0 * cyc_scale
        ring = np.abs(FR - fr) < 1.0 / n
        med = float(np.median(S[ring]))
        pk = 0.0
        for ang in angles:
            iy = int(np.argmin(np.abs(f - fr * np.sin(np.radians(ang)))))
            ix = int(np.argmin(np.abs(f - fr * np.cos(np.radians(ang)))))
            pk = max(pk, float(S[iy - 1:iy + 2, ix - 1:ix + 2].max()))
        out[name] = pk / med if med > 0 else float("nan")
    return out


def lattice_score(scan: Scan, A: np.ndarray, box_mm: tuple[float, float, float, float],
                  own: tuple[int, ...]) -> dict[str, Any]:
    """Mean lattice ratios over raw-scan windows of LAT_WIN_PX at 2400 dpi (the same 1.016 mm at any scan dpi)
    tiled over box_mm (one centred window when the box is smaller than a window)."""
    x0, y0, x1, y1 = box_mm
    win_px = int(round(LAT_WIN_PX * scan.dpi / SCAN_DPI_NOMINAL))
    win_mm = win_px / scan.px_per_mm
    cyc_scale = SCAN_DPI_NOMINAL / scan.dpi

    def centres(a: float, b: float) -> np.ndarray:
        k = max(1, int((b - a) // win_mm))
        return a + 0.5 * (b - a) + (np.arange(k) - 0.5 * (k - 1)) * win_mm
    per: dict[str, list[float]] = defaultdict(list)
    n = 0
    for cy in centres(y0, y1):
        for cx in centres(x0, x1):
            col = A[0, 0] * cx + A[0, 1] * cy + A[0, 2]
            row = A[1, 0] * cx + A[1, 1] * cy + A[1, 2]
            r0, c0 = int(round(row)) - win_px // 2, int(round(col)) - win_px // 2
            win = scan.crop(r0, r0 + win_px, c0, c0 + win_px)
            if win.shape[:2] != (win_px, win_px):
                continue
            g = win[..., list(own)].mean(axis=2)
            if g.std() < 0.5:
                continue
            for k, v in lattice_ratios(g, cyc_scale).items():
                per[k].append(v)
            n += 1
    lat = {k: nanstat(v, np.mean) for k, v in per.items()}
    score = max(lat.values()) if lat else float("nan")
    return {"windows": n, "lattice": lat, "score": score,
            "best_lattice": max(lat, key=lambda k: lat[k]) if lat else None}


def read_bar(scan: Scan, A: np.ndarray, bar: dict[str, Any], dpi: float,
             sub: int = SUB_PX_PER_DOT) -> dict[str, Any]:
    x, y, w, h = rect_dots(bar, dpi)
    dot_mm = 25.4 / dpi
    box = (x * dot_mm + BAR_ERODE_MM, y * dot_mm + BAR_ERODE_MM,
           (x + w) * dot_mm - BAR_ERODE_MM, (y + h) * dot_mm - BAR_ERODE_MM)
    step = dot_mm / sub
    px = sample_rect(scan, A, np.arange(box[0], box[2], step), np.arange(box[1], box[3], step),
                     order=0).reshape(-1, 3)
    rgb = [int(v) for v in bar["rgb"]]
    own = own_channels(rgb)
    lat = lattice_score(scan, A, box, own)
    name = bar.get("colour", bar.get("colour_name", bar.get("name", bar.get("id"))))
    return {"id": bar.get("id"), "colour": name, "rgb": rgb, "section": bar.get("section"),
            "neutral": bar.get("neutral"), "x_dots": x, "y_dots": y, "w_dots": w, "h_dots": h,
            "mean_rgb": px.mean(0).tolist(), "sd_rgb": px.std(0).tolist(),
            "own": [("R", "G", "B")[c] for c in own],
            "lattice_windows": lat["windows"], "lattice": lat["lattice"], "screen_score": lat["score"],
            "best_lattice": lat["best_lattice"],
            "verdict": ("unscreened" if lat["score"] <= UNSCREENED_MAX else "screened")
            if np.isfinite(lat["score"]) else "flat"}


# ---------------------------------------------------------------- report

def pct(v: float) -> str:
    return "   -  " if v is None or not np.isfinite(v) else f"{100 * v:6.2f}"


def band_line(s: dict[str, Any], ref: dict[str, Any] | None) -> str:
    pe = " ".join(f"{pl}{pct(s['plane'][pl]['hard_err_best'])}" for pl in PLANES
                  if np.isfinite(s["plane"][pl]["hard_err_best"]))
    d = s["density"]
    line = (f"  {s['name']:7s} {s['family']:11s} c{s['cell_dots']} {str(s['method']):6s} "
            f"{str(s['neutral']):7s} match {str(s['matching']):7s} obj {s['objects']:2d}"
            f" win {s['windows']:4d}"
            f"  state% loo {pct(s['state_err_loo']['mean'])}/{pct(s['state_err_loo']['median'])}"
            f" p90 {pct(s['state_err_loo']['p90'])} cross {pct(s['state_err_cross']['mean'])}"
            f" band {pct(s['state_err_band']['mean'])}"
            f" [single pose loo {pct(s['state_err_loo_singlepose']['mean'])}"
            f" band {pct(s['state_err_band_singlepose']['mean'])}]"
            f" [whole cell loo {pct(s['state_err_loo_wholecell']['mean'])}"
            f" band {pct(s['state_err_band_wholecell']['mean'])}"
            f" MI {d['mi_band_wholecell_bits_per_cell']:.3f}]  plane best% {pe}"
            f"  MI {d['mi_band_bits_per_cell']:.3f}/{d['raw_bits_per_cell']:.2f} b/cell"
            f" = {d['mi_band_bits_per_mm2']:.1f}/{d['raw_bits_per_mm2']:.1f} b/mm2")
    if s["reg_nominal"]:
        line += f"  REG-NOMINAL x{s['reg_nominal']}"
    if s["reg_edge"]:
        line += f"  REG-EDGE x{s['reg_edge']}"
    po = s["pose"]
    line += ("\n          plane pose vs C (median px): " + " ".join(
        f"{pl} {po[pl]['dy_vs_C_median']:+.2f},{po[pl]['dx_vs_C_median']:+.2f}" for pl in "MYK"
        if np.isfinite(po[pl]["dy_vs_C_median"]))
        + "  flags " + " ".join(f"{pl}:" + ",".join(f"{f}{c}" for f, c in po[pl]["flags"].items() if c)
                                for pl in PLANES))
    if ref:
        line += (f"\n          S12 patches {'/'.join(ref['arms'])} {s['method']} (n {ref['n_patches']}): "
                 f"loo {pct(ref['state_err_loo'])} cross {pct(ref['state_err_cross'])}"
                 f" [single pose loo {pct(ref['state_err_loo_singlepose'])}]  plane best% "
                 + " ".join(f"{pl}{pct(v)}" for pl, v in ref["plane_hard_err_best"].items()
                            if np.isfinite(v)))
    if s.get("layout"):
        line += "\n" + layout_line(s)
    return line


def layout_line(s: dict[str, Any]) -> str:
    """The band's layout reading (given the true state): errors %, layout MI, combined bits."""
    lo, d = s["layout"], s["density"]
    per = " ".join(f"{k} {pct(v['err']).strip()}/{v['mi_bits']:.2f}b" for k, v in lo["per_state"].items())
    return (f"          layout given state: err {pct(lo['err'])}% (n {lo['n']}) orientation "
            f"{pct(lo['orient_err'])}% (n {lo['n_orient']}) phase {pct(lo['phase_err'])}% (n {lo['n_phase']})"
            f"  psf {lo['psf_dots_median']:.2f} dot  per state err%/MI: {per}"
            f"\n          bits/cell: state MI {d['mi_band_bits_per_cell']:.3f} + layout "
            f"{lo['mi_layout_bits_per_cell']:.3f} = {lo['combined_band_bits_per_cell']:.3f}"
            f" = {lo['combined_band_bits_per_mm2']:.1f} b/mm2  [whole cell state MI: "
            f"{lo['combined_band_wholecell_bits_per_cell']:.3f} b/cell = "
            f"{lo['combined_band_wholecell_bits_per_mm2']:.1f} b/mm2]")


def compare(a: dict[str, Any], b: dict[str, Any], ra: list[float], rb: list[float]) -> str:
    va, vb = np.array(ra, np.float64), np.array(rb, np.float64)
    se = math.sqrt(va.var(ddof=1) / len(va) + vb.var(ddof=1) / len(vb)) if len(va) > 1 and len(vb) > 1 else 0
    return (f"{a['name']} {pct(a['state_err_loo']['mean'])}% vs "
            f"{b['name']} {pct(b['state_err_loo']['mean'])}%"
            f"  (band-means {pct(a['state_err_band']['mean'])} vs {pct(b['state_err_band']['mean'])});"
            f"  diff {100 * (va.mean() - vb.mean()):+.2f} pp +- {100 * se:.2f}"
            " (window se, spatially correlated)"
            "  plane best% " + " / ".join(
                f"{pl} {pct(a['plane'][pl]['hard_err_best']).strip()}:"
                f"{pct(b['plane'][pl]['hard_err_best']).strip()}"
                for pl in PLANES if np.isfinite(a["plane"][pl]["hard_err_best"])))


def profile_line(s: dict[str, Any], axis: str) -> str:
    return " ".join(f"{p['mm']:.0f}:{100 * p['state_err_loo']:.1f}" for p in s[f"profile_{axis}"])


def offset_profile_line(s: dict[str, Any], pl: str) -> str:
    return " ".join(f"{p['mm']:.0f}:{p[f'{pl}_dy_vs_C_px']:+.1f},{p[f'{pl}_dx_vs_C_px']:+.1f}"
                    for p in s["profile_col"] if np.isfinite(p[f"{pl}_dy_vs_C_px"]))


def strip_verdict(bars: list[dict[str, Any]], section: str, pred: Any) -> tuple[str, list[dict[str, Any]]]:
    """'screened' / 'unscreened' / 'mixed' / 'missing' over the section's bars that satisfy pred."""
    sel = [b for b in bars if str(b["section"]) == section and pred(b)]
    v = {b["verdict"] for b in sel}
    return ("missing" if not sel else v.pop() if len(v) == 1 else "mixed"), sel


def matching_witness(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """The pure-cyan (0, 255, 255) bars in strip A (matching default) vs strip B (matching off)."""
    va, sa = strip_verdict(bars, "A", lambda b: tuple(b["rgb"]) == WITNESS_RGB)
    vb, sb = strip_verdict(bars, "B", lambda b: tuple(b["rgb"]) == WITNESS_RGB)
    rule = {("screened", "unscreened"): "per-object matching control works",
            ("unscreened", "unscreened"): "page-global latch",
            ("screened", "screened"): "no per-image effect"}
    reading = rule.get((va, vb), "outside the reading rule")
    vm, sm = strip_verdict(bars, "B", lambda b: str(b["colour"]) == "M-solid")
    return {"A": va, "B": vb, "reading": reading, "B_M_solid": vm,
            "A_scores": [b["screen_score"] for b in sa], "B_scores": [b["screen_score"] for b in sb],
            "B_M_solid_scores": [b["screen_score"] for b in sm]}


def print_report(sums: list[dict[str, Any]], refs: dict[str, Any], rows: list[dict[str, Any]],
                 bars: list[dict[str, Any]], sub: int = SUB_PX_PER_DOT) -> list[dict[str, Any]]:
    print("\n== bands (state error % over windows: loo mean/median, p90, cross, band-wide means; "
          "plane = best-threshold hard error %; MI from the band-means confusion) ==")
    for s in sums:
        print(band_line(s, refs.get(s["name"])))
    by = {s["name"]: s for s in sums}
    errs: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        errs[r["band"]].append(r["state_err_loo"])
    comps = []
    print("\n== comparisons ==")
    for a, b, title in COMPARISONS:
        if a in by and b in by:
            print(f"  {title}: {compare(by[a], by[b], errs[a], errs[b])}")
            comps.append({"a": a, "b": b, "title": title, "a_mean": by[a]["state_err_loo"]["mean"],
                          "b_mean": by[b]["state_err_loo"]["mean"]})
    if "A2" in by:
        s, ref = by["A2"], refs.get("A2")
        print(f"  cmy8 at page scale: A2 loo {pct(s['state_err_loo']['mean'])}% band "
              f"{pct(s['state_err_band']['mean'])}%  plane best% "
              + " ".join(f"{pl} {pct(s['plane'][pl]['hard_err_best']).strip()}" for pl in "CMY")
              + (f"   (S12 patch A17 loo {pct(ref['state_err_loo']).strip()}%)" if ref else ""))
    print("\n== profiles: window loo state error % by x mm (column) and y mm (row) ==")
    for s in sums:
        print(f"  {s['name']} x: {profile_line(s, 'col')}")
        print(f"  {s['name']} y: {profile_line(s, 'row')}")
    lay = [s for s in sums if s.get("layout")]
    if lay:
        print("\n== layout given state: window orientation error % by x mm (column; - = no orientation "
              "axis) ==")
        for s in lay:
            print(f"  {s['name']} x: " + " ".join(
                f"{p['mm']:.0f}:{100 * p['orient_err']:.1f}" if np.isfinite(p["orient_err"])
                else f"{p['mm']:.0f}:-"
                for p in s["profile_col"]))
    print(f"\n== plane offset vs C by x mm (column median dy,dx scan px; {sub} px = 1 dot) ==")
    for s in sums:
        for pl in "MYK":
            line = offset_profile_line(s, pl)
            if line:
                print(f"  {s['name']} {pl}-C: {line}")
    print(f"\n== bars (lattice score = known-lattice peak over ring median, {LAT_WIN_PX}-px windows, own "
          f"channel(s); <= {UNSCREENED_MAX:.0f} unscreened) ==")
    order = {c: i for i, c in enumerate(BAR_ORDER)}
    for sec in sorted({str(b["section"]) for b in bars}):
        print(f"  section {sec}:")
        for b in sorted((b for b in bars if str(b["section"]) == sec),
                        key=lambda b: (order.get(str(b["colour"]), len(order)), b["y_dots"], b["x_dots"])):
            lat = " ".join(f"{k} {v:5.1f}" for k, v in b["lattice"].items())
            print(f"    {str(b['colour']):12s} rgb {tuple(b['rgb'])!s:16s} {str(b['neutral']):7s} "
                  f"mean RGB {b['mean_rgb'][0]:5.1f} {b['mean_rgb'][1]:5.1f} {b['mean_rgb'][2]:5.1f}  "
                  f"own {''.join(b['own']):3s} score {b['screen_score']:6.1f} {b['verdict']:10s} [{lat}]")
    wit = matching_witness(bars)
    sc = "/".join(f"{v:.1f}" for v in wit["A_scores"]), "/".join(f"{v:.1f}" for v in wit["B_scores"])
    print(f"\n== matching witness: cyan {WITNESS_RGB} bar, strip A (matching default) {wit['A']} "
          f"(score {sc[0]}) vs strip B (matching off) {wit['B']} (score {sc[1]}) ==")
    print("  reading rule: A screened / B solid = per-object matching control works; both solid = "
          "page-global latch; both screened = no per-image effect")
    print(f"  -> {wit['reading']}")
    print(f"  strip B M-solid bar: {wit['B_M_solid']} (score "
          + "/".join(f"{v:.1f}" for v in wit["B_M_solid_scores"]) + ")")
    comps.append({"witness": wit})
    return comps


# ---------------------------------------------------------------- outputs

def ramp(v: np.ndarray, vmax: float) -> np.ndarray:
    """White 0 -> yellow -> red -> black at vmax; NaN grey."""
    t = np.clip(v / vmax, 0, 1)
    stops = np.array([0, 1 / 3, 2 / 3, 1])
    cols = np.array([[255, 255, 255], [255, 220, 0], [220, 0, 0], [0, 0, 0]], np.float64)
    out = np.stack([np.interp(t, stops, cols[:, c]) for c in range(3)], -1)
    out[~np.isfinite(v)] = 128
    return out.astype(np.uint8)


def write_map(rs: list[dict[str, Any]], path: Path, scale_px: int = 12) -> float:
    nr = 1 + max(r["grid_row"] for r in rs)
    nc = 1 + max(r["grid_col"] for r in rs)
    g = np.full((nr, nc), np.nan)
    for r in rs:
        g[r["grid_row"], r["grid_col"]] = r["state_err_loo"]
    vmax = max(0.02, float(np.nanquantile(g, 0.99)))
    im = np.kron(ramp(g, vmax), np.ones((scale_px, scale_px, 1), np.uint8))
    Image.fromarray(im).save(path)
    return vmax


def write_csv(path: Path, head: list[str], lines: list[list[Any]]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(head)
        w.writerows(lines)


def f4(v: Any) -> str:
    return "" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.4f}"


def window_csv(rows: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    head = ["id", "band", "section", "matching", "tile", "grid_row", "grid_col", "x_dots", "y_dots", "xc_mm",
            "yc_mm", "cell_dots", "cells", "reg_ok", "reg_edge", "reg_peak", "reg_dx_mm", "reg_dy_mm",
            "n_neighbours", "state_err_loo", "state_err_cross", "state_err_band", "state_err_loo_singlepose",
            "state_err_cross_singlepose", "state_err_band_singlepose"]
    for pl in PLANES:
        head += [f"{pl}_pose_flag", f"{pl}_pose_peak", f"{pl}_pose_dy_px", f"{pl}_pose_dx_px",
                 f"{pl}_dy_vs_C_px", f"{pl}_dx_vs_C_px"]
    for pl in PLANES:
        head += [f"{pl}_n1", f"{pl}_n0", f"{pl}_dprime", f"{pl}_hard_err", f"{pl}_hard_err_best",
                 f"{pl}_hard_err_best_singlepose"]
    head += ["state_err_loo_wholecell", "state_err_cross_wholecell", "state_err_band_wholecell"]
    head += ["layout_err", "orient_err", "phase_err", "n_layout_cells"]
    lines = []
    for r in rows:
        ln: list[Any] = [r["id"], r["band"], r["section"], r["matching"], r["tile"], r["grid_row"],
                         r["grid_col"], r["x_dots"], r["y_dots"], f"{r['xc_mm']:.3f}", f"{r['yc_mm']:.3f}",
                         r["cell_dots"], r["cells"], int(r["reg_ok"]), int(r["reg_edge"]),
                         f"{r['reg_peak']:.3f}", f"{r['reg_dx_mm']:+.4f}", f"{r['reg_dy_mm']:+.4f}",
                         r["n_neighbours"], f4(r["state_err_loo"]), f4(r["state_err_cross"]),
                         f4(r["state_err_band"]), f4(r["state_err_loo_singlepose"]),
                         f4(r["state_err_cross_singlepose"]), f4(r["state_err_band_singlepose"])]
        for pl in PLANES:
            q = r["poses"][pl]
            ln += [q["flag"], f4(q["peak"]), f4(q["dy_px"]), f4(q["dx_px"]), f4(q["dy_vs_C_px"]),
                   f4(q["dx_vs_C_px"])]
        for pl in PLANES:
            p = r["planes"][pl]
            ln += [p["n1"], p["n0"], f4(p["dprime"]), f4(p["hard_err"]), f4(p["hard_err_best"]),
                   f4(r["planes_singlepose"][pl]["hard_err_best"])]
        ln += [f4(r["state_err_loo_wholecell"]), f4(r["state_err_cross_wholecell"]),
               f4(r["state_err_band_wholecell"])]
        ln += [f4(r.get("layout_err")), f4(r.get("orient_err")), f4(r.get("phase_err")),
               r.get("n_layout_cells", "")]
        lines.append(ln)
    return head, lines


def band_csv(sums: list[dict[str, Any]], refs: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    head = ["name", "section", "matching", "family", "alphabet", "cell_dots", "method", "neutral", "objects",
            "windows", "reg_nominal", "reg_edge"]
    for k in ("loo", "cross", "band"):
        head += [f"state_err_{k}_{m}" for m in ("mean", "median", "p90", "max")]
        head += [f"state_err_{k}_singlepose_{m}" for m in ("mean", "median", "p90", "max")]
    for pl in "MYK":
        head += [f"{pl}_dy_vs_C_median_px", f"{pl}_dx_vs_C_median_px"]
    for pl in PLANES:
        head += [f"{pl}_hard_err", f"{pl}_hard_err_best", f"{pl}_dprime"]
    head += ["cells_per_mm2", "raw_bits_per_cell", "raw_bits_per_mm2", "mi_loo_bits_per_cell",
             "mi_band_bits_per_cell", "mi_band_bits_per_mm2", "s12_arms", "s12_state_err_loo",
             "s12_state_err_cross", "s12_state_err_loo_singlepose"]
    for k in ("loo", "cross", "band"):
        head += [f"state_err_{k}_wholecell_{m}" for m in ("mean", "median", "p90", "max")]
    head += ["mi_band_wholecell_bits_per_cell"]
    head += ["layout_err", "orient_err", "phase_err", "n_layout_cells", "mi_layout_bits_per_cell",
             "combined_bits_per_cell", "combined_bits_per_mm2"]
    lines = []
    for s in sums:
        ln: list[Any] = [s["name"], s["section"], s["matching"], s["family"], "|".join(s["alphabet"]),
                         s["cell_dots"],
                         s["method"], s["neutral"], s["objects"], s["windows"], s["reg_nominal"],
                         s["reg_edge"]]
        for k in ("loo", "cross", "band"):
            ln += [f4(s[f"state_err_{k}"][m]) for m in ("mean", "median", "p90", "max")]
            ln += [f4(s[f"state_err_{k}_singlepose"][m]) for m in ("mean", "median", "p90", "max")]
        for pl in "MYK":
            ln += [f4(s["pose"][pl]["dy_vs_C_median"]), f4(s["pose"][pl]["dx_vs_C_median"])]
        for pl in PLANES:
            ln += [f4(s["plane"][pl][m]) for m in ("hard_err", "hard_err_best", "dprime")]
        d = s["density"]
        ref = refs.get(s["name"])
        ln += [f"{d['cells_per_mm2']:.2f}", f"{d['raw_bits_per_cell']:.4f}", f"{d['raw_bits_per_mm2']:.2f}",
               f4(d["mi_loo_bits_per_cell"]), f4(d["mi_band_bits_per_cell"]),
               f"{d['mi_band_bits_per_mm2']:.2f}",
               "|".join(ref["arms"]) if ref else "", f4(ref["state_err_loo"]) if ref else "",
               f4(ref["state_err_cross"]) if ref else "", f4(ref["state_err_loo_singlepose"]) if ref else ""]
        for k in ("loo", "cross", "band"):
            ln += [f4(s[f"state_err_{k}_wholecell"][m]) for m in ("mean", "median", "p90", "max")]
        ln += [f4(d["mi_band_wholecell_bits_per_cell"])]
        lo = s.get("layout")
        ln += ([f4(lo["err"]), f4(lo["orient_err"]), f4(lo["phase_err"]), lo["n"],
                f4(lo["mi_layout_bits_per_cell"]), f4(lo["combined_band_bits_per_cell"]),
                f"{lo['combined_band_bits_per_mm2']:.2f}"] if lo else [""] * 7)
        lines.append(ln)
    return head, lines


def bar_csv(bars: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    head = ["id", "colour", "section", "neutral", "rgb", "x_dots", "y_dots", "w_dots", "h_dots", "mean_R",
            "mean_G", "mean_B", "sd_R", "sd_G", "sd_B", "own", "lattice_windows", *LATTICES, "screen_score",
            "best_lattice", "verdict"]
    lines = [[b["id"], b["colour"], b["section"], b["neutral"], "|".join(str(v) for v in b["rgb"]),
              b["x_dots"], b["y_dots"], b["w_dots"], b["h_dots"], *(f"{v:.2f}" for v in b["mean_rgb"]),
              *(f"{v:.2f}" for v in b["sd_rgb"]), "".join(b["own"]), b["lattice_windows"],
              *(f4(b["lattice"].get(k)) for k in LATTICES), f4(b["screen_score"]), b["best_lattice"],
              b["verdict"]] for b in bars]
    return head, lines


def layout_bands(npz: Any, data_bands: list[dict[str, Any]],
                 arrays: dict[str, tuple[np.ndarray, np.ndarray]]) -> dict[str, tuple[Catalogue, np.ndarray]]:
    """Bands whose layout_catalogue gives some state more than one entry and whose npz carries layouts_<band>:
    (catalogue, layouts), each checked against planes_<band> (refuses on a mismatch — contract fork)."""
    out = {}
    for b in data_bands:
        cat = catalogue_of(b, states_of(b))
        if cat is None or not cat.has_axis():
            continue
        states, planes = arrays[b["name"]]
        lt = layouts_of(npz, b, states.shape)
        if lt is None:
            print(f"  band {b['name']}: a layout catalogue but no layouts_ array; layout not scored")
            continue
        bad = check_catalogue(cat, states, lt, planes)
        if bad:
            raise SystemExit(f"band {b['name']}: {bad} cells where the layout catalogue does not reproduce "
                             "planes_ — contract fork")
        out[b["name"]] = (cat, lt)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", required=True, help="RGB TIFF of the printed sheet (at --scan-dpi)")
    ap.add_argument("--manifest", required=True, help="the generator's S14 manifest JSON")
    ap.add_argument("--bands", default=None, help="the bands npz (default <manifest dir>/<tag>-bands.npz)")
    ap.add_argument("--patch-ref", default=None, help="S12-ps-mixture-patches.csv (patch-level reference)")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--tag", default=None, help="output file prefix (default: the manifest's tag)")
    ap.add_argument("--max-resid-mm", type=float, default=0.3, help="refuse above this fiducial residual")
    ap.add_argument("--scale-tol", type=float, default=0.01,
                    help="allowed relative scale error vs --scan-dpi")
    ap.add_argument("--scan-dpi", type=float, default=SCAN_DPI_NOMINAL,
                    help="the scan's resolution (2400 or 4800; rectified px per dot = scan dpi / print dpi)")
    args = ap.parse_args()
    mpath = Path(args.manifest)
    man = json.loads(mpath.read_text())
    for key in ("tag", "dpi", "fiducials", "bands"):
        if key not in man:
            raise SystemExit(f"manifest {mpath} lacks '{key}'")
    dpi = float(man["dpi"])
    sub = sub_px_per_dot(args.scan_dpi, dpi)
    npz_path = Path(args.bands) if args.bands else mpath.parent / f"{man['tag']}-bands.npz"
    npz = np.load(npz_path)
    tag = args.tag or man["tag"]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    frame = page_frame(man)
    arrays = {b["name"]: a for b in man["bands"] if (a := band_arrays(npz, b, dpi)) is not None}
    data_bands = [b for b in man["bands"] if b["name"] in arrays]
    windows = man.get("windows") or [w for b in data_bands for w in tile_windows(b, dpi)]
    lays = layout_bands(npz, data_bands, arrays)
    # the path alone at the default: the experiments/041 verifiers' in-memory Scan stand-ins take only that
    scan = (Scan(Path(args.scan)) if args.scan_dpi == SCAN_DPI_NOMINAL
            else Scan(Path(args.scan), args.scan_dpi))
    print(f"{tag}: scan {scan.w} x {scan.h} px, {len(data_bands)} data bands, {len(windows)} windows, "
          f"{len(man.get('bars', []))} bars")
    if sub != SUB_PX_PER_DOT or lays:
        print(f"  scan {args.scan_dpi:.0f} dpi = {sub} px per dot; layout axis on {len(lays)} band(s)"
              + (": " + ", ".join(lays) if lays else ""))
    A, fit = fit_page(scan, frame, args.max_resid_mm, args.scale_tol)
    dot_mm = 25.4 / dpi
    rects = [(x * dot_mm, y * dot_mm, (x + w) * dot_mm, (y + h) * dot_mm)
             for e in [*man["bands"], *man.get("bars", []), *man["fiducials"]]
             for x, y, w, h in [rect_dots(e, dpi)]]
    gwhite = page_white(scan, A, frame, rects)
    print(f"page white (margins) R {gwhite[0]:.1f} G {gwhite[1]:.1f} B {gwhite[2]:.1f}")
    rows = []
    for w in windows:
        b = band_of(data_bands, w["band"])
        try:
            rows.append(read_window(scan, A, w, b, *arrays[b["name"]], dpi, gwhite, sub, lays.get(b["name"])))
        except ValueError as exc:
            print(f"  window {w['id']}: skipped ({exc})")
    classify_windows(rows, {b["name"]: states_of(b) for b in data_bands})
    by_band: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_band[r["band"]].append(r)
    sums = [band_summary(b, by_band[b["name"]], dpi, lays[b["name"]][0] if b["name"] in lays else None)
            for b in data_bands if by_band[b["name"]]]
    ref_path = Path(args.patch_ref) if args.patch_ref else None
    refs = {b["name"]: ref for b in data_bands if (ref := patch_reference(ref_path, b)) is not None}
    bars = [read_bar(scan, A, bar, dpi, sub) for bar in man.get("bars", [])]
    n_nom = sum(1 for r in rows if not r["reg_ok"])
    n_edge = sum(1 for r in rows if r["reg_edge"])
    shift = max((abs(r["reg_dx_mm"]) + abs(r["reg_dy_mm"]) for r in rows), default=0.0)
    peaks = np.array([r["reg_peak"] for r in rows])
    print(f"{len(rows)} windows read; registration fell back to nominal on {n_nom}; peak on the "
          f"+/- {SEARCH_MM} mm boundary on {n_edge}; |reg shift| max "
          f"{shift:.3f} mm; peak min {peaks.min():.3f} median {np.median(peaks):.3f}")
    comps = print_report(sums, refs, rows, bars, sub)
    maps = {}
    for s in sums:
        maps[s["name"]] = write_map(by_band[s["name"]], out / f"{tag}-map-{s['name']}.png")
    print("\nmaps: " + ", ".join(f"{k} (black = {100 * v:.1f} %)" for k, v in maps.items()))
    write_csv(out / f"{tag}-windows.csv", *window_csv(rows))
    write_csv(out / f"{tag}-bands.csv", *band_csv(sums, refs))
    write_csv(out / f"{tag}-bars.csv", *bar_csv(bars))
    for r in rows:
        for k in ("_X", "_X1", "_XW", "_y", "_lay"):
            r.pop(k, None)
    summary = {"tag": tag, "scan": str(args.scan), "manifest": str(mpath), "bands_npz": str(npz_path),
               "job_sha256": man.get("sha256"), "job_bytes": man.get("bytes"), "fit": fit,
               "page_white": gwhite.tolist(), "n_windows_read": len(rows), "n_reg_nominal": n_nom,
               "n_reg_edge": n_edge, "search_mm": SEARCH_MM, "scan_dpi": args.scan_dpi, "px_per_dot": sub,
               "pose": "per plane (e041_mixture_readout.plane_poses): own dot mask vs own spectrally "
                       f"unmixed coverage, +/- {plane_search_px(sub)} px around the OR-ed pose; R sampled at "
                       "C's pose, G at M's, B at Y's; *_singlepose = every channel at the OR-ed pose",
               "classifier": "nearest mean in RGB; loo = the window itself, leave-one-out; "
                             "cross = the up-to-8 "
                             "neighbouring windows of the band; band = all windows of the band",
               "plane_channels": {"C": "R", "M": "G", "Y": "B", "K": "max(R,G,B)"},
               "lattices": {k: {"cycles_per_px": f * SCAN_DPI_NOMINAL / args.scan_dpi, "angles_deg": list(a)}
                            for k, (f, a) in LATTICES.items()},
               "unscreened_max": UNSCREENED_MAX, "map_vmax": maps, "bands": sums, "patch_reference": refs,
               "comparisons": comps, "bars": bars, "windows": rows}
    (out / f"{tag}-summary.json").write_text(json.dumps(jsonable(summary), indent=1))
    print(f"wrote {out}/{tag}-{{windows,bands,bars}}.csv, {tag}-summary.json, {len(maps)} maps")


if __name__ == "__main__":
    main()

"""e041 S11 — read the PCL XL mixture probe sheet: which alphabets survive a mixed field on the M281?

The S11 sheet (tag "S11-pclxl-mixture", the contract in the e041 log) prints 93 x 93-dot pattern squares over
a 93 x 24-dot solid bar.  Every pattern is a field of c3 (31 x 31 cells of 3 x 3 dots) or c2 (46 x 46 cells
of 2 x 2 dots, last dot row/column white) cells whose states are drawn iid from an ARM's alphabet (W, C, M,
Y, K, engine overlaps CM/CY/MY/CMY, or overlaps built from single-toner dots inside the cell), under two
halftone methods (default, eHighLPI) and two neutral axes (process black, toner black).  The generator writes
the manifest and, beside it, <tag>-patterns.npz with per patch "states_<id>" (cells x cells uint8, an index
into the patch's alphabet list) and "planes_<id>" (4 x 93 x 93 uint8, C, M, Y, K ink per dot).  This
instrument works from that npz and never regenerates a pattern; states_sha256 is checked against it.

Per patch, on a 2400 dpi RGB scan (this main reads 2400 only; the shared plane_poses takes `sub` px per dot
and its search radius in those px — plane_search_px(sub), 3 dots — so e041_scale_readout runs it at 4800):

1. page fit: the five fiducials, as-is or turned 180 deg (measure.e041_probe_readout.fit_page, imported);
2. registration: the pattern square plus its bar and a 2 x SEARCH_MM margin resampled page-aligned at 4 px
   per dot (1 dot = 4 px at 2400 dpi; a c3 cell = 12 px, a c2 cell = 8 px); the template = the dot-level ink
   mask with all four planes OR-ed, plus the bar (all ink), plus SEARCH_MM of white around both, registered
   against darkness = 255 - min(R, G, B) by FFT cross-correlation within +/- SEARCH_MM
   (measure.e041_gt_compare.xcorr_shift); below REG_MIN_PEAK the nominal position is kept (reg_ok 0);
2b. PER-PLANE pose (041.5f: the M281 lays yellow 1-2.5 dots off cyan, varying across the page, and the
   OR-ed pose follows the dark cyan): every plane present gets its own pose within +/- PLANE_SEARCH_PX of
   the OR-ed one — its own dot mask correlated with its own coverage, spectrally unmixed per pixel from
   the R, G, B, max(R, G, B) densities (plane_poses: the mixing matrix by least squares at the current
   poses, PLANE_UNMIX_ITERS rounds); flags ok / edge (peak on the search boundary) / weak (OR-ed pose
   kept) / collinear (masks correlated, e.g. {C, M}: biased, kept out of the offset statistics);
3. per CELL the mean R, G, B over a centre box of half the cell (e041_probe_readout.cell_samples), each
   channel at its plane's pose: R at C's, G at M's, B at Y's (sample_per_plane; an absent plane's channel
   at the OR-ed pose; an alphabet whose only plane is K: all three at K's pose; the K plane's own
   statistic reads RGB at K's pose; a state carrying K ink is scored through RGB at K's pose for every
   channel whose plane it lacks — the features follow the HYPOTHESIS, never the cell's true state:
   hypothesis_features).  The same at the single OR-ed
   pose is kept beside it: every *_singlepose column is the previous readout, so before and after sit in
   one CSV;
4. per PLANE (C -> R, M -> G, Y -> B, K -> MAX of the cell's R, G, B means): the plane's ink fraction per
   cell from the npz; cells at fraction 1 against cells at fraction 0 (each class >= MIN_CLASS cells):
   inked and blank means, d' = (blank - inked) / pooled sd, hard error at the midpoint
   (e041_probe_readout.channel_stats), and beside it hard_err_best = the error at the best single threshold
   (the midpoint is wrong when the blank class is multi-modal, e.g. magenta toner's own darkening of B in
   the Y plane's blank cells); at every intermediate fraction (dot-mixed arms) the channel mean.
   Two deviations from the S11 contract, both forced: K reads max(R, G, B), not min — every single toner
   has a channel near 0, so min cannot tell K from C, M or Y; only K (or the composite) darkens the lightest
   channel.  And the C, M, Y planes leave out cells carrying any K ink (K darkens every channel; with them
   the C plane's blank class would hold black cells).  The K plane uses every cell;
5. STATE error, the figure of merit of an alphabet: a nearest-mean classifier in RGB (Euclidean) over the
   arm's alphabet.  "loo" = means fitted on the patch itself, LEAVE-ONE-OUT (each cell is classified against
   its own state's mean with that cell removed, closed form); "cross" = means fitted on all cells of the
   other replicates of the same (arm, fraction, method, neutral), never on the patch itself.
   "construction" = dotmix when any plane has a cell at an intermediate ink fraction, else solid;  Confusion
   matrices (rows true, columns predicted, alphabet order) in the summary JSON;
6. the solid bar (first non-white state of the alphabet): interior eroded 0.3 mm -> mean and sd of R, G, B.
   No lattice score: e041_probe_readout has a lattice method only on a 256 px window centred on the pattern,
   none for the bar (the bar's eroded interior is ~40 px tall), so it is skipped.

Figures of merit: state_err_loo (per patch, and its mean over replicates per (arm, fraction, method,
neutral)), state_err_cross (the stability of the state means across positions), per-plane hard_err and d';
each with its *_singlepose twin.  Per patch the plane offsets (dy, dx vs the OR-ed pose and vs C, scan px:
4 px = 1 dot), printed per OFFSET_BIN_MM bin of x, and the state error per alphabet family (uniform
fraction, pooled over cells) single pose -> per plane.
Outputs in --out: <tag>-patches.csv (one row per patch: registration, bar, white, per plane, per state),
<tag>-summary.json (fit, every patch with confusion matrices, the arm table, the comparisons, the ranking);
on stdout a table per ARM (per fraction x method x neutral: replicates, mean state error loo / cross,
per-plane hard error), the side-by-side comparisons (c3 vs c2, palette, neutral axis: the configurations that
differ in exactly that one field), and the ranking of every configuration by mean loo state error.

    PYTHONPATH=src:. env/bin/python -m measure.e041_mixture_readout \\
        --scan <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S11/captures/S11-canon-2400rgb.tiff \\
        --manifest <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S11/jobs/S11-pclxl-mixture.manifest.json \\
        --out build/e041/mixture
    (--patterns P overrides the npz path; default <manifest dir>/<the manifest's patterns_npz.file>, else
    <manifest dir>/<tag>-patterns.npz.)

Smoke test without printer or scanner: measure/e041_mixture_synth.py paints the same contract.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage

from measure.e041_gt_compare import xcorr_shift
from measure.e041_probe_readout import (SOLID_ERODE_MM, SUB_PX_PER_DOT, Geometry, Scan, cell_samples,
                                        channel_stats, fit_page, footprints_mm, jsonable, local_white,
                                        page_white, sample_rect)

PLANES = ("C", "M", "Y", "K")
STATE_ORDER = ("W", "C", "M", "Y", "K", "CM", "CY", "MY", "CMY")
SEARCH_MM = 0.3
REG_MIN_PEAK = 0.25
MIN_CLASS = 5
FRAC_DECIMALS = 4
PLANE_SEARCH_DOTS = 3                  # per-plane search radius around the OR-ed pose, printed dots
PLANE_SEARCH_PX = PLANE_SEARCH_DOTS * SUB_PX_PER_DOT   # ... in scan px at 2400 dpi (plane_search_px)
PLANE_MIN_PEAK = 0.2                   # below: the plane keeps the OR-ed pose (flag "weak")
PLANE_MIN_INK, PLANE_MAX_INK = 0.02, 0.98   # a plane registers only when its dot fraction lies in between
PLANE_UNMIX_ITERS = 3
UNMIX_MAX_CORR = 0.75                  # dot masks correlated beyond this: no cross term until poses differ
UNMIX_MIN_SEP_PX = 0.5                 # ... by at least this much, px at 2400 (else collinear with the
                                       # constant); 1/8 dot, scaled by sub / SUB_PX_PER_DOT at any dpi
OFFSET_BIN_MM = 50.0


# ---------------------------------------------------------------- inputs

def load_manifest(path: Path) -> dict[str, Any]:
    man = json.loads(path.read_text())
    for key in ("tag", "dpi", "page_mm", "fiducials", "patch_px", "patches"):
        if key not in man:
            raise SystemExit(f"manifest {path} lacks '{key}'")
    return man


def patterns_path(manifest: Path, man: dict[str, Any], override: str | None) -> Path:
    """--patterns, else the manifest's patterns_npz file (S12 references S11's), else <tag>-patterns.npz."""
    if override:
        return Path(override)
    named = man.get("patterns_npz", {}).get("file")
    return manifest.parent / (named or f"{man['tag']}-patterns.npz")


def patch_arrays(npz: Any, p: dict[str, Any], pattern_dots: int) -> tuple[np.ndarray, np.ndarray]:
    """(states cells x cells uint8, planes 4 x dots x dots uint8) of patch p, checked against the manifest."""
    pid = p["id"]
    try:
        states = np.asarray(npz[f"states_{pid}"], np.uint8)
        planes = np.asarray(npz[f"planes_{pid}"], np.uint8)
    except KeyError as exc:
        raise SystemExit(f"patterns npz lacks {exc} — contract fork")
    cells, cd = int(p["cells"]), int(p["cell_dots"])
    if states.shape != (cells, cells) or planes.shape != (4, pattern_dots, pattern_dots):
        raise SystemExit(f"patch {pid}: states {states.shape} / planes {planes.shape} do not match "
                         f"{cells} cells, {pattern_dots} dots — contract fork")
    if cells * cd > pattern_dots:
        raise SystemExit(f"patch {pid}: {cells} x {cd} dots exceed the {pattern_dots}-dot square")
    sha = hashlib.sha256(np.ascontiguousarray(states).tobytes()).hexdigest()
    if p.get("states_sha256") not in (None, sha):
        raise SystemExit(f"patch {pid}: states_sha256 mismatch — contract fork")
    if int(states.max()) >= len(p["alphabet"]):
        raise SystemExit(f"patch {pid}: state index {int(states.max())} outside its alphabet {p['alphabet']}")
    return states, planes


def cell_fractions(planes: np.ndarray, cells: int, cell_dots: int) -> np.ndarray:
    """(4, cells, cells): each plane's ink fraction over each cell's dots."""
    n = cells * cell_dots
    return planes[:, :n, :n].astype(np.float64).reshape(4, cells, cell_dots, cells, cell_dots).mean((2, 4))


def bar_state(alphabet: list[str]) -> str:
    return next((s for s in alphabet if s != "W"), alphabet[0])


# ---------------------------------------------------------------- per patch

def register(rect: np.ndarray, ink: np.ndarray, n_bar: int, s_px: int) -> tuple[float, float, float]:
    """(oy, ox, peak): the pattern's top-left in rect px.  rect carries a 2 s_px margin on every side."""
    n_pat = ink.shape[0]
    tm = np.zeros((n_pat + n_bar + 2 * s_px, n_pat + 2 * s_px), np.float32)
    tm[s_px:s_px + n_pat, s_px:s_px + n_pat] = ink
    tm[s_px + n_pat:s_px + n_pat + n_bar, s_px:s_px + n_pat] = 1.0
    dark = 255.0 - rect.min(axis=2)
    dy, dx, peak = xcorr_shift(dark, tm, s_px)
    return dy + s_px, dx + s_px, peak


def density(rect: np.ndarray, white: np.ndarray) -> np.ndarray:
    """(H, W, 4) optical density over paper white: R, G, B, and max(R, G, B) (the K channel)."""
    w = np.maximum(np.asarray(white, np.float32), 1.0)
    d = -np.log10(np.maximum(rect, 1.0) / w)
    dmax = -np.log10(np.maximum(rect.max(axis=2), 1.0) / float(w.max()))
    return np.concatenate([d, dmax[..., None]], -1).astype(np.float32)


def place(t: np.ndarray, py: float, px: float, size: int) -> np.ndarray:
    """t on a (size, size) zero canvas with its top-left at (py, px), bilinear sub-pixel."""
    canvas = np.zeros((size, size), np.float32)
    iy, ix = int(np.floor(py)), int(np.floor(px))
    h, w = t.shape
    canvas[iy:iy + h, ix:ix + w] = t[:max(0, size - iy), :max(0, size - ix)]
    return ndimage.shift(canvas, (py - iy, px - ix), order=1, mode="constant")


def plane_search_px(sub: int) -> int:
    """The per-plane search radius in rectified px at `sub` px per dot (12 at 2400 dpi, 24 at 4800)."""
    return PLANE_SEARCH_DOTS * sub


def plane_poses(rect: np.ndarray, planes: np.ndarray, oy: float, ox: float, white: np.ndarray,
                search_px: int = PLANE_SEARCH_PX, sub: int = SUB_PX_PER_DOT,
                use_px: np.ndarray | None = None) -> dict[str, dict[str, Any]]:
    """Per plane present (dot fraction in [PLANE_MIN_INK, PLANE_MAX_INK]): the top-left of that plane's own
    dot mask in rect px, searched within +/- search_px of the OR-ed pose (oy, ox).

    Optical density is additive over toner layers, so per pixel D_ch = sum_k a_ch,k t_k + b_ch over the
    channels R, G, B, max(R, G, B) and the present planes' coverages t_k.  Each round: the mixing matrix
    (a, b) by least squares of every channel's density on the present planes' dot masks at their current
    poses; every pixel unmixed into plane coverages through its pseudo-inverse (spectral, so a neighbour
    plane's cross-talk is removed where it actually lies, whatever its pose); each plane's coverage map
    correlated with its own mask (FFT, parabolic sub-pixel peak, e041_gt_compare.xcorr_shift).
    PLANE_UNMIX_ITERS rounds from the OR-ed pose.  Two masks correlated beyond UNMIX_MAX_CORR (e.g. {C, M}
    with no white: C = 1 - M) are collinear with the constant at one pose, so while their poses lie within
    UNMIX_MIN_SEP_PX the cross term is left out of the fit of the other's own channel (R for C, G for M,
    B for Y, max for K).  Flags: "ok", "edge" (integer peak on the search boundary: the true offset may lie
    beyond; the estimate is kept), "weak" (peak < PLANE_MIN_PEAK: the OR-ed pose is kept), "collinear"
    (the plane's mask correlates with another's beyond UNMIX_MAX_CORR: the pose is used for sampling but
    is biased — on a synthetic {C, M} page with 1.5 px blur a true 2.0 px M - C separation reads 3.0, the
    blurred density being non-linear where a 2 px white gap meets a 2 px overlap — so it stays out of the
    offset statistics).  Planes not present are absent from the dict.  rect is resampled at `sub` px per
    dot (4 at 2400 dpi, 8 at 4800); search_px is in those px.  use_px (bool, rect's shape; None = every
    pixel) restricts the evidence: the mixing fit uses only those pixels, and every other pixel of a
    coverage map is set to the used pixels' mean before the correlation (no weight) — for a template that
    covers only part of the window (e041_layout_readout: the solid cells), so ink the template does not
    model cannot pull the peak.  No plane present (an all-white window): there is no guard; np.stack of no
    plane raises numpy's ValueError, which e041_scale_readout's window loop reports as "skipped"."""
    n = planes.shape[1] * sub
    P = search_px
    size = n + 2 * P
    r0, c0 = int(round(oy)) - P, int(round(ox)) - P
    if r0 < 0 or c0 < 0 or r0 + size > rect.shape[0] or c0 + size > rect.shape[1]:
        raise ValueError("plane search window outside the resampled rect")
    D = density(rect[r0:r0 + size, c0:c0 + size], white).reshape(-1, 4)
    blk = np.ones((sub,) * 2, np.float32)
    present = [k for k in range(4) if PLANE_MIN_INK <= float(planes[k].mean()) <= PLANE_MAX_INK]
    T = {k: np.kron(planes[k].astype(np.float32), blk) for k in present}
    pose = {k: (oy - r0, ox - c0) for k in present}
    peak = {k: float("nan") for k in present}
    flag = {k: "weak" for k in present}
    corr = np.atleast_2d(np.corrcoef(np.stack([planes[k].ravel().astype(np.float64) for k in present])))
    collinear = {k: any(abs(corr[a, b]) >= UNMIX_MAX_CORR for b in range(len(present)) if b != a)
                 for a, k in enumerate(present)}
    ones = np.ones(size * size, np.float32)
    min_sep = UNMIX_MIN_SEP_PX * sub / SUB_PX_PER_DOT
    U = None if use_px is None else use_px[r0:r0 + size, c0:c0 + size].reshape(-1)
    for _ in range(PLANE_UNMIX_ITERS):
        canv = np.stack([place(T[k], *pose[k], size).ravel() for k in present] + [ones], 1)
        mix = np.zeros((4, len(present) + 1))
        for ch in range(4):
            own = present.index(ch) if ch in present else None
            use = [b for b, j in enumerate(present)
                   if own is None or b == own or abs(corr[own, b]) < UNMIX_MAX_CORR
                   or float(np.hypot(*np.subtract(pose[j], pose[present[own]]))) >= min_sep]
            cols = use + [len(present)]
            if U is None:
                coef, *_ = np.linalg.lstsq(canv[:, cols], D[:, ch], rcond=None)
            else:
                coef, *_ = np.linalg.lstsq(canv[U][:, cols], D[U, ch], rcond=None)
            mix[ch, cols] = coef
        cover = (D - mix[:, -1]) @ np.linalg.pinv(mix[:, :-1]).T
        new = {}
        if U is not None:
            cover = np.where(U[:, None], cover, cover[U].mean(0))
        for b, k in enumerate(present):
            dy, dx, pk = xcorr_shift(cover[:, b].reshape(size, size), T[k], P)
            peak[k] = pk
            if pk < PLANE_MIN_PEAK:
                new[k], flag[k] = (oy - r0, ox - c0), "weak"
            else:
                edge = min(dy, dx) < 0.5 or max(dy, dx) > 2 * P - 0.5
                new[k], flag[k] = (dy, dx), "edge" if edge else "collinear" if collinear[k] else "ok"
        pose = new
    return {PLANES[k]: {"oy": r0 + pose[k][0], "ox": c0 + pose[k][1], "peak": peak[k], "flag": flag[k]}
            for k in present}


def sample_per_plane(rect: np.ndarray, poses: dict[str, dict[str, Any]], oy: float, ox: float, cells: int,
                     cell_px: int, box: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(vals, vals_k): per cell R at C's pose, G at M's, B at Y's (a channel whose plane is absent: the
    OR-ed pose; an alphabet with K as its only plane: all three at K's pose); vals_k = RGB at K's pose
    (the OR-ed pose without K): the K plane's own statistic, and the K hypothesis's features
    (hypothesis_features)."""
    def at(pl: str) -> tuple[float, float]:
        return (poses[pl]["oy"], poses[pl]["ox"]) if pl in poses else (oy, ox)
    if not any(pl in poses for pl in "CMY") and "K" in poses:
        vk = cell_samples(rect, *at("K"), cells, cell_px, box)
        return vk, vk
    cache: dict[tuple[float, float], np.ndarray] = {}

    def get(p: tuple[float, float]) -> np.ndarray:
        if p not in cache:
            cache[p] = cell_samples(rect, p[0], p[1], cells, cell_px, box)
        return cache[p]
    vals = np.stack([get(at(pl))[..., c] for c, pl in enumerate("CMY")], -1)
    return vals, get(at("K"))


def state_plane_sets(frac: np.ndarray, y: np.ndarray, n_states: int) -> np.ndarray:
    """(S, 4) bool: plane k belongs to state s when its mean ink fraction over the state's cells >= 0.25."""
    f = frac.reshape(4, -1).T
    out = np.zeros((n_states, 4), bool)
    for st in range(n_states):
        sel = y == st
        if sel.any():
            out[st] = f[sel].mean(0) >= 0.25
    return out


def hypothesis_features(vals: np.ndarray, vals_k: np.ndarray, sets: np.ndarray) -> np.ndarray:
    """(N, S, 3): the RGB a cell shows UNDER EACH STATE HYPOTHESIS.  A state carrying K ink reads every
    channel whose own plane (R C, G M, B Y) it lacks at K's pose — toner K at all three — and every other
    state reads the per-plane sample.  The classifier compares a cell to state s through s's own
    features, so the pose follows the hypothesis, never the cell's true state (no truth in the input).
    Why not K's pose for K cells only (that would choose the pose by the truth), nor the OR-ed pose: on
    S11 K lies 4-5 px above C on the left half (K - C dy), and with K cells read at C/M/Y's poses cmyk5
    pooled 1.49 / 2.36 % (c3 default / eHighLPI) and 12.3 / 23.1 % (c2); with K's own hypothesis
    features 0.73 / 0.97 % and 8.7 / 16.3 % (single OR-ed pose: 0.62 / 1.42 %, 13.9 / 26.1 %).  What
    still costs c3 its margin over the OR-ed pose is W read as Y or C: at Y's and C's poses a white cell
    takes in its K neighbours' ink (K darkens every channel) — channel cross-talk, not registration."""
    use_k = sets[:, 3:4] & ~sets[:, :3]
    return np.where(use_k[None], vals_k[:, None, :], vals[:, None, :])


def plane_values(vals: np.ndarray, k: int) -> np.ndarray:
    return vals.max(axis=-1) if PLANES[k] == "K" else vals[..., k]


def best_threshold_err(v: np.ndarray, ink: np.ndarray) -> float:
    """Lowest hard error over every threshold, ink on the dark side."""
    order = np.argsort(v, kind="stable")
    i = ink[order].astype(np.int64)
    err = (i.sum() - np.concatenate([[0], np.cumsum(i)])) + np.concatenate([[0], np.cumsum(1 - i)])
    return float(err.min() / len(v))


def plane_stats(v: np.ndarray, frac: np.ndarray, keep: np.ndarray) -> dict[str, Any]:
    ink, blank = (frac >= 1 - 1e-9) & keep, (frac <= 1e-9) & keep
    out: dict[str, Any] = {"n1": int(ink.sum()), "n0": int(blank.sum()), "n_excluded_k": int((~keep).sum())}
    if out["n1"] >= MIN_CLASS and out["n0"] >= MIN_CLASS:
        sel = ink | blank
        out.update(channel_stats(v[sel], ink[sel]))
        out["hard_err_best"] = best_threshold_err(v[sel], ink[sel])
    else:
        out.update({"inked": float(v[ink].mean()) if out["n1"] else float("nan"),
                    "blank": float(v[blank].mean()) if out["n0"] else float("nan"),
                    "dprime": float("nan"), "hard_err": float("nan"), "hard_err_best": float("nan")})
    mid = (~ink) & (~blank) & keep
    fr = np.round(frac[mid], FRAC_DECIMALS)
    out["intermediate"] = {f"{f:.{FRAC_DECIMALS}f}": {"n": int((fr == f).sum()),
                                                     "mean": float(v[mid][fr == f].mean())}
                           for f in np.unique(fr)}
    return out


def pose_record(poses: dict[str, dict[str, Any]], oy: float, ox: float) -> dict[str, dict[str, Any]]:
    """Per plane: offset from the OR-ed pose and from C's (scan px; vs C only where both flags are ok or
    edge), peak and flag; absent planes flagged."""
    out: dict[str, dict[str, Any]] = {}
    c = poses.get("C")
    c_ok = c is not None and c["flag"] in ("ok", "edge")
    for pl in PLANES:
        q = poses.get(pl)
        if q is None:
            out[pl] = {"flag": "absent", "peak": float("nan"), "dy_px": float("nan"), "dx_px": float("nan"),
                       "dy_vs_C_px": float("nan"), "dx_vs_C_px": float("nan")}
            continue
        rel = c_ok and q["flag"] in ("ok", "edge")
        out[pl] = {"flag": q["flag"], "peak": q["peak"], "dy_px": q["oy"] - oy, "dx_px": q["ox"] - ox,
                   "dy_vs_C_px": q["oy"] - c["oy"] if rel else float("nan"),
                   "dx_vs_C_px": q["ox"] - c["ox"] if rel else float("nan")}
    return out


def read_patch(scan: Scan, A: np.ndarray, p: dict[str, Any], states: np.ndarray, planes: np.ndarray,
               g: Geometry, white: np.ndarray) -> dict[str, Any]:
    cells, cd = int(p["cells"]), int(p["cell_dots"])
    step = g.dot_mm / SUB_PX_PER_DOT
    cell_px = cd * SUB_PX_PER_DOT
    n_pat, n_bar = g.pattern_dots * SUB_PX_PER_DOT, g.solid_dots * SUB_PX_PER_DOT
    s_px = int(round(SEARCH_MM / step))
    m_px = 2 * s_px
    x0, y0 = float(p["x_mm"]), float(p["y_mm"])
    bx = np.arange(x0 + SOLID_ERODE_MM, x0 + g.pattern_dots * g.dot_mm - SOLID_ERODE_MM, step)
    by0 = y0 + g.pattern_dots * g.dot_mm
    by = np.arange(by0 + SOLID_ERODE_MM, by0 + g.solid_dots * g.dot_mm - SOLID_ERODE_MM, step)
    solid = sample_rect(scan, A, bx, by, order=0).reshape(-1, 3)
    kx, ky = np.arange(n_pat + 2 * m_px), np.arange(n_pat + n_bar + 2 * m_px)
    rect = sample_rect(scan, A, x0 + (kx - m_px) * step, y0 + (ky - m_px) * step)
    ink = np.kron(planes.max(axis=0).astype(np.float32), np.ones((SUB_PX_PER_DOT,) * 2, np.float32))
    oy, ox, peak = register(rect, ink, n_bar, s_px)
    reg_ok = bool(peak >= REG_MIN_PEAK)
    if not reg_ok:
        oy = ox = float(m_px)
    vals1 = cell_samples(rect, oy, ox, cells, cell_px)
    poses = plane_poses(rect, planes, oy, ox, white)
    vals, vals_k = sample_per_plane(rect, poses, oy, ox, cells, cell_px)
    frac = cell_fractions(planes, cells, cd)
    row: dict[str, Any] = {k: p.get(k) for k in ("id", "arm", "fraction", "method", "neutral", "band",
                                                 "seed", "replicate")}
    row["family"] = p.get("family") or "|".join(p["alphabet"])
    row.update({"x_mm": x0, "y_mm": y0, "xc_mm": x0 + 0.5 * g.pattern_dots * g.dot_mm, "cell_dots": cd,
                "cells": cells, "alphabet": list(p["alphabet"]),
                "palette": {k: list(v) for k, v in p.get("palette", {}).items()},
                "bar_state": bar_state(list(p["alphabet"])), "solid": solid.mean(0).tolist(),
                "solid_sd": solid.std(0).tolist(), "white": white.tolist(), "reg_ok": reg_ok,
                "reg_peak": float(peak), "reg_dy_mm": (oy - m_px) * step, "reg_dx_mm": (ox - m_px) * step})
    no_k = frac[3] <= 1e-9
    every = np.ones_like(no_k)
    row["planes"] = {PLANES[k]: plane_stats(plane_values(vals_k if k == 3 else vals, k), frac[k],
                                            every if k == 3 else no_k) for k in range(4)}
    row["planes_singlepose"] = {PLANES[k]: plane_stats(plane_values(vals1, k), frac[k],
                                                       every if k == 3 else no_k) for k in range(4)}
    row["poses"] = pose_record(poses, oy, ox)
    row["construction"] = "dotmix" if bool(((frac > 1e-9) & (frac < 1 - 1e-9)).any()) else "solid"
    y = states.reshape(-1).astype(np.int64)
    row["_X"] = hypothesis_features(vals.reshape(-1, 3).astype(np.float64),
                                    vals_k.reshape(-1, 3).astype(np.float64),
                                    state_plane_sets(frac, y, len(p["alphabet"])))
    row["_X1"] = vals1.reshape(-1, 3).astype(np.float64)
    row["_y"] = y
    return row


# ---------------------------------------------------------------- state classifier

def class_means(X: np.ndarray, y: np.ndarray, n_states: int) -> tuple[np.ndarray, np.ndarray]:
    """Per-state mean RGB and count; X is (N, 3), or (N, S, 3) per-hypothesis features (state s's mean
    over its own cells' column s)."""
    if X.ndim == 3:
        X = X[np.arange(len(y)), y]
    n = np.bincount(y, minlength=n_states).astype(np.float64)
    s = np.stack([np.bincount(y, weights=X[:, c], minlength=n_states) for c in range(3)], -1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mu = s / n[:, None]
    return mu, n


def classify(X: np.ndarray, y: np.ndarray, mu: np.ndarray, n: np.ndarray | None) -> np.ndarray:
    """Nearest mean; with n given, the own-class mean is the leave-one-out mean (n_s mu_s - x)/(n_s - 1).
    X (N, 3), or (N, S, 3): the distance to state s from the cell's features under hypothesis s."""
    XH = X if X.ndim == 3 else X[:, None, :]
    d = ((XH - mu[None, :, :]) ** 2).sum(-1)
    d[:, ~np.isfinite(mu).all(1)] = np.inf
    if n is not None:
        idx = np.arange(len(y))
        X = X[idx, y] if X.ndim == 3 else X
        ns = n[y]
        with np.errstate(invalid="ignore", divide="ignore"):
            loo = (ns[:, None] * mu[y] - X) / (ns[:, None] - 1)
        own = ((X - loo) ** 2).sum(-1)
        d[idx, y] = np.where(ns > 1, own, np.inf)
    return d.argmin(1)


def state_report(y: np.ndarray, pred: np.ndarray, alphabet: list[str]) -> dict[str, Any]:
    S = len(alphabet)
    conf = np.zeros((S, S), np.int64)
    np.add.at(conf, (y, pred), 1)
    per = {}
    for s, name in enumerate(alphabet):
        tot = int(conf[s].sum())
        per[name] = {"n": tot, "err": float(1 - conf[s, s] / tot) if tot else float("nan")}
    return {"err": float((pred != y).mean()), "confusion": conf.tolist(), "per_state": per}


def group_key(r: dict[str, Any]) -> tuple[Any, ...]:
    return (r["arm"], r["fraction"], r["method"], r["neutral"])


def classify_all(rows: list[dict[str, Any]]) -> None:
    """Per-plane-sampled RGB (_X) -> state_loo / state_cross; the single OR-ed pose (_X1) -> the same with
    the suffix _singlepose."""
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[group_key(r)].append(r)
    for xkey, sfx in (("_X", ""), ("_X1", "_singlepose")):
        for r in rows:
            S = len(r["alphabet"])
            X, y = r[xkey], r["_y"]
            mu, n = class_means(X, y, S)
            r[f"state_loo{sfx}"] = state_report(y, classify(X, y, mu, n), r["alphabet"])
            r[f"state_means{sfx}"] = {name: mu[s].tolist() for s, name in enumerate(r["alphabet"])}
            others = [o for o in groups[group_key(r)] if o is not r and o["alphabet"] == r["alphabet"]]
            if others:
                mu_x, _ = class_means(np.concatenate([o[xkey] for o in others]),
                                      np.concatenate([o["_y"] for o in others]), S)
                r[f"state_cross{sfx}"] = state_report(y, classify(X, y, mu_x, None), r["alphabet"])
            else:
                r[f"state_cross{sfx}"] = None
            r[f"state_err_loo{sfx}"] = r[f"state_loo{sfx}"]["err"]
            cr = r[f"state_cross{sfx}"]
            r[f"state_err_cross{sfx}"] = cr["err"] if cr else float("nan")


# ---------------------------------------------------------------- outputs

def state_names(rows: list[dict[str, Any]]) -> list[str]:
    seen = {s for r in rows for s in r["alphabet"]}
    return [s for s in STATE_ORDER if s in seen] + sorted(seen - set(STATE_ORDER))


def f4(v: Any) -> str:
    return "" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.4f}"


def csv_table(rows: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    names = state_names(rows)
    head = ["id", "arm", "family", "cell_dots", "construction", "fraction", "method", "neutral", "band",
            "replicate", "seed", "x_mm",
            "y_mm", "alphabet", "reg_ok", "reg_peak", "reg_dx_mm", "reg_dy_mm", "bar_state", "solid_R",
            "solid_G", "solid_B", "white_R", "white_G", "white_B", "state_err_loo", "state_err_cross",
            "state_err_loo_singlepose", "state_err_cross_singlepose"]
    for pl in PLANES:
        head += [f"{pl}_pose_flag", f"{pl}_pose_peak", f"{pl}_pose_dy_px", f"{pl}_pose_dx_px",
                 f"{pl}_dy_vs_C_px", f"{pl}_dx_vs_C_px"]
    for pl in PLANES:
        head += [f"{pl}_n1", f"{pl}_n0", f"{pl}_n_excluded_k", f"{pl}_inked", f"{pl}_blank", f"{pl}_dprime",
                 f"{pl}_hard_err", f"{pl}_hard_err_best", f"{pl}_intermediate", f"{pl}_dprime_singlepose",
                 f"{pl}_hard_err_best_singlepose"]
    for s in names:
        head += [f"n_{s}", f"err_loo_{s}", f"err_cross_{s}", f"mean_R_{s}", f"mean_G_{s}", f"mean_B_{s}"]
    out = []
    for r in rows:
        line: list[Any] = [r["id"], r["arm"], r["family"], r["cell_dots"], r["construction"], r["fraction"],
                           r["method"], r["neutral"],
                           r["band"], r["replicate"], r["seed"], f"{r['x_mm']:.4f}", f"{r['y_mm']:.4f}",
                           "|".join(r["alphabet"]), int(r["reg_ok"]), f"{r['reg_peak']:.3f}",
                           f"{r['reg_dx_mm']:+.4f}", f"{r['reg_dy_mm']:+.4f}", r["bar_state"],
                           *(f"{v:.2f}" for v in r["solid"]), *(f"{v:.2f}" for v in r["white"]),
                           f4(r["state_err_loo"]), f4(r["state_err_cross"]),
                           f4(r["state_err_loo_singlepose"]), f4(r["state_err_cross_singlepose"])]
        for pl in PLANES:
            q = r["poses"][pl]
            line += [q["flag"], f4(q["peak"]), f4(q["dy_px"]), f4(q["dx_px"]), f4(q["dy_vs_C_px"]),
                     f4(q["dx_vs_C_px"])]
        for pl in PLANES:
            s = r["planes"][pl]
            s1 = r["planes_singlepose"][pl]
            inter = ";".join(f"{k}:{v['mean']:.1f}(n{v['n']})" for k, v in s["intermediate"].items())
            line += [s["n1"], s["n0"], s["n_excluded_k"], f4(s["inked"]), f4(s["blank"]), f4(s["dprime"]),
                     f4(s["hard_err"]), f4(s["hard_err_best"]), inter, f4(s1["dprime"]),
                     f4(s1["hard_err_best"])]
        for s in names:
            if s not in r["alphabet"]:
                line += [""] * 6
                continue
            ps = r["state_loo"]["per_state"][s]
            cr = r["state_cross"]["per_state"][s]["err"] if r["state_cross"] else None
            line += [ps["n"], f4(ps["err"]), f4(cr), *(f4(v) for v in r["state_means"][s])]
        out.append(line)
    return head, out


def nanmean(vs: list[float]) -> float:
    a = np.array([v for v in vs if v is not None and np.isfinite(v)], np.float64)
    return float(a.mean()) if a.size else float("nan")


def config_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per (arm, fraction, method, neutral): replicate means of the figures of merit."""
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[group_key(r)].append(r)
    out = []
    for key, rs in groups.items():
        r0 = rs[0]
        out.append({"arm": key[0], "fraction": key[1], "method": key[2], "neutral": key[3],
                    "cell_dots": r0["cell_dots"], "construction": r0["construction"],
                    "alphabet": r0["alphabet"], "palette": r0["palette"],
                    "replicates": len(rs), "ids": [r["id"] for r in rs],
                    "state_err_loo": nanmean([r["state_err_loo"] for r in rs]),
                    "state_err_loo_max": max(r["state_err_loo"] for r in rs),
                    "state_err_cross": nanmean([r["state_err_cross"] for r in rs]),
                    "state_err_loo_singlepose": nanmean([r["state_err_loo_singlepose"] for r in rs]),
                    "state_err_cross_singlepose": nanmean([r["state_err_cross_singlepose"] for r in rs]),
                    "plane_hard_err": {pl: nanmean([r["planes"][pl]["hard_err"] for r in rs])
                                       for pl in PLANES},
                    "plane_hard_err_best": {pl: nanmean([r["planes"][pl]["hard_err_best"] for r in rs])
                                            for pl in PLANES},
                    "plane_dprime": {pl: nanmean([r["planes"][pl]["dprime"] for r in rs]) for pl in PLANES},
                    "reg_ok": sum(int(r["reg_ok"]) for r in rs)})
    return out


def cfg_line(c: dict[str, Any]) -> str:
    pe = " ".join(f"{pl} {c['plane_hard_err'][pl]:.3f}/{c['plane_hard_err_best'][pl]:.3f}"
                  if np.isfinite(c["plane_hard_err"][pl]) else f"{pl}      -    " for pl in PLANES)
    return (f"    {str(c['fraction']):10s} {str(c['method']):8s} {str(c['neutral']):7s}"
            f" reps {c['replicates']}"
            f"  state loo {c['state_err_loo']:.4f} (max {c['state_err_loo_max']:.4f})"
            f"  cross {c['state_err_cross']:.4f} [single pose loo {c['state_err_loo_singlepose']:.4f}]"
            f"   plane hard err mid/best {pe}"
            + ("" if c["reg_ok"] == c["replicates"] else f"  REG-NOMINAL x{c['replicates'] - c['reg_ok']}"))


def palette_sig(pal: dict[str, list[int]]) -> str:
    """The single-toner entries only; overlap entries belong to the construction axis."""
    return " ".join(f"{k}={','.join(str(v) for v in pal[k])}" for k in STATE_ORDER[:5] if k in pal)


def comparisons(cfgs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Configurations equal in everything but one field (cell_dots, palette, neutral axis, construction)."""
    def key(c: dict[str, Any], drop: str) -> tuple[Any, ...]:
        fields = {"alphabet": tuple(c["alphabet"]), "palette": palette_sig(c["palette"]),
                  "cell_dots": c["cell_dots"], "neutral": c["neutral"], "construction": c["construction"],
                  "fraction": c["fraction"],
                  "method": c["method"]}
        fields.pop(drop)
        return tuple(fields.values())
    out: dict[str, list[dict[str, Any]]] = {}
    for axis in ("cell_dots", "palette", "neutral", "construction"):
        groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for c in cfgs:
            groups[key(c, axis)].append(c)
        rows = []
        for k, cs in groups.items():
            vals = {palette_sig(c["palette"]) if axis == "palette" else c[axis] for c in cs}
            if len(vals) < 2:
                continue
            rows.append({"alphabet": cs[0]["alphabet"], "fraction": cs[0]["fraction"],
                         "method": cs[0]["method"],
                         "side": [{"arm": c["arm"], axis: palette_sig(c["palette"]) if axis == "palette"
                                   else c[axis], "cell_dots": c["cell_dots"], "neutral": c["neutral"],
                                   "state_err_loo": c["state_err_loo"],
                                   "state_err_cross": c["state_err_cross"]}
                                  for c in sorted(cs, key=lambda c: str(c["arm"]))]})
        out[axis] = rows
    return out


def print_report(cfgs: list[dict[str, Any]], comps: dict[str, list[dict[str, Any]]],
                 arms_meta: Any) -> list[dict[str, Any]]:
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in cfgs:
        by_arm[str(c["arm"])].append(c)
    for arm in sorted(by_arm):
        cs = by_arm[arm]
        c0 = cs[0]
        desc = arm_desc(arms_meta, arm)
        print(f"\n{arm}  c{c0['cell_dots']} {c0['construction']}  {{{','.join(c0['alphabet'])}}}"
              f"  {palette_sig(c0['palette'])}"
              + (f"  — {desc}" if desc else ""))
        for c in sorted(cs, key=lambda c: (str(c["fraction"]), str(c["method"]), str(c["neutral"]))):
            print(cfg_line(c))
    for axis, title in (("cell_dots", "c3 vs c2"), ("palette", "palette"), ("neutral", "neutral axis"),
                        ("construction", "engine overlap vs dot mix")):
        print(f"\n== {title}: configurations differing only in {axis} ==")
        for row in comps[axis]:
            side = "  |  ".join(f"{s['arm']} [{s[axis]}] loo {s['state_err_loo']:.4f} cross "
                                f"{s['state_err_cross']:.4f}" for s in row["side"])
            print(f"  {{{','.join(row['alphabet'])}}} {row['fraction']} {row['method']}:  {side}")
    rank = sorted(cfgs, key=lambda c: (c["state_err_loo"], str(c["arm"])))
    print("\n== ranking by mean leave-one-out state error ==")
    for i, c in enumerate(rank, 1):
        print(f"  {i:3d}. {str(c['arm']):5s} c{c['cell_dots']} {{{','.join(c['alphabet'])}}} {c['fraction']} "
              f"{c['method']} {c['neutral']}: loo {c['state_err_loo']:.4f} cross {c['state_err_cross']:.4f}")
    return [{"rank": i, "arm": c["arm"], "fraction": c["fraction"], "method": c["method"],
             "neutral": c["neutral"], "state_err_loo": c["state_err_loo"]} for i, c in enumerate(rank, 1)]


def family_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Uniform fraction only, per (family, cell size, method): the state error pooled over every cell of
    every patch (errors / cells), loo and cross, single pose (before) and per plane (after)."""
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r["fraction"] == "uniform":
            groups[(r["family"], r["cell_dots"], r["method"])].append(r)
    out = []
    for (fam, cd, method), rs in sorted(groups.items(), key=lambda kv: tuple(str(v) for v in kv[0])):
        ent: dict[str, Any] = {"family": fam, "cell_dots": cd, "method": method, "patches": len(rs),
                               "arms": sorted({str(r["arm"]) for r in rs})}
        for k in ("loo", "cross"):
            for sfx in ("_singlepose", ""):
                reps = [r[f"state_{k}{sfx}"] for r in rs if r[f"state_{k}{sfx}"]]
                n = sum(int(np.sum(rep["confusion"])) for rep in reps)
                wrong = sum(int(np.sum(rep["confusion"]) - np.trace(rep["confusion"])) for rep in reps)
                ent[f"state_err_{k}{sfx}"] = wrong / n if n else float("nan")
        out.append(ent)
    return out


def offset_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per plane vs C, per OFFSET_BIN_MM bin of the patch centre x: n, median and p10/p90 of dy and dx (scan
    px), over patches where both poses were measured (flag ok or edge), edge count beside."""
    out = []
    for pl in ("M", "Y", "K"):
        bins: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            q = r["poses"][pl]
            if np.isfinite(q["dy_vs_C_px"]):
                bins[int(r["xc_mm"] // OFFSET_BIN_MM)].append(r)
        for b in sorted(bins):
            rs = bins[b]
            dy = np.array([r["poses"][pl]["dy_vs_C_px"] for r in rs])
            dx = np.array([r["poses"][pl]["dx_vs_C_px"] for r in rs])
            edge = sum(1 for r in rs if "edge" in (r["poses"][pl]["flag"], r["poses"]["C"]["flag"]))
            out.append({"plane": pl, "x0_mm": b * OFFSET_BIN_MM, "x1_mm": (b + 1) * OFFSET_BIN_MM,
                        "n": len(rs), "edge": edge,
                        "dy_median": float(np.median(dy)), "dy_p10": float(np.quantile(dy, 0.1)),
                        "dy_p90": float(np.quantile(dy, 0.9)), "dy_min": float(dy.min()),
                        "dx_median": float(np.median(dx)), "dx_p10": float(np.quantile(dx, 0.1)),
                        "dx_p90": float(np.quantile(dx, 0.9))})
    return out


def print_pose_report(fams: list[dict[str, Any]], offs: list[dict[str, Any]],
                      rows: list[dict[str, Any]]) -> None:
    flags: dict[str, dict[str, int]] = {pl: defaultdict(int) for pl in PLANES}
    for r in rows:
        for pl in PLANES:
            flags[pl][r["poses"][pl]["flag"]] += 1
    print("\n== per-plane pose flags (patches): "
          + "; ".join(f"{pl} " + " ".join(f"{k} {v}" for k, v in sorted(flags[pl].items())) for pl in PLANES))
    print("\n== per-plane offset vs C by patch-centre x (scan px; 4 px = 1 dot): n, median dy [p10, p90] "
          "(min), median dx [p10, p90] ==")
    for o in offs:
        print(f"  {o['plane']}-C x {o['x0_mm']:3.0f}-{o['x1_mm']:3.0f} mm n {o['n']:3d} edge {o['edge']:2d}"
              f"  dy {o['dy_median']:+6.2f} [{o['dy_p10']:+6.2f}, {o['dy_p90']:+6.2f}] ({o['dy_min']:+6.2f})"
              f"  dx {o['dx_median']:+6.2f} [{o['dx_p10']:+6.2f}, {o['dx_p90']:+6.2f}]")
    print("\n== state error per alphabet family, uniform fraction, pooled over cells: "
          "single pose -> per plane ==")
    for f in fams:
        print(f"  {str(f['family']):12s} c{f['cell_dots']} {str(f['method']):8s} patches {f['patches']:3d}"
              f"  loo {f['state_err_loo_singlepose']:.4f} -> {f['state_err_loo']:.4f}"
              f"  cross {f['state_err_cross_singlepose']:.4f} -> {f['state_err_cross']:.4f}"
              f"  ({','.join(f['arms'])})")


def arm_desc(arms_meta: Any, arm: str) -> str:
    """Best-effort description from the manifest's arms table (a dict keyed by arm or a list of dicts)."""
    ent: Any = None
    if isinstance(arms_meta, dict):
        ent = arms_meta.get(arm)
    elif isinstance(arms_meta, list):
        ent = next((a for a in arms_meta
                    if isinstance(a, dict) and str(a.get("arm", a.get("id"))) == arm), None)
    if isinstance(ent, str):
        return ent
    if isinstance(ent, dict):
        for k in ("desc", "description", "note", "name"):
            if isinstance(ent.get(k), str):
                return ent[k]
    return ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", required=True, help="2400 dpi RGB TIFF of the printed S11 sheet")
    ap.add_argument("--manifest", required=True, help="the generator's S11 manifest JSON")
    ap.add_argument("--patterns", default=None,
                    help="the patterns npz (default: the manifest's patterns_npz file, else "
                         "<tag>-patterns.npz)")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--tag", default=None, help="output file prefix (default: the manifest's tag)")
    ap.add_argument("--max-resid-mm", type=float, default=0.3, help="refuse above this fiducial residual")
    ap.add_argument("--scale-tol", type=float, default=0.01, help="allowed relative scale error vs 2400 dpi")
    args = ap.parse_args()
    mpath = Path(args.manifest)
    man = load_manifest(mpath)
    npz = np.load(patterns_path(mpath, man, args.patterns))
    pp = man["patch_px"]
    g = Geometry(25.4 / float(man["dpi"]), int(pp["pattern_dots"]), int(pp["solid_dots"]), 1, 1)
    tag = args.tag or man["tag"]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scan = Scan(Path(args.scan))
    print(f"{tag}: scan {scan.w} x {scan.h} px, {len(man['patches'])} patches, "
          f"{len(man['fiducials'])} fiducials")
    A, fit = fit_page(scan, man, args.max_resid_mm, args.scale_tol)
    rects = footprints_mm(man, g)
    gwhite = page_white(scan, A, man, rects)
    print(f"page white (gap median) R {gwhite[0]:.1f} G {gwhite[1]:.1f} B {gwhite[2]:.1f}")
    pw = g.pattern_dots * g.dot_mm
    ph = (g.pattern_dots + g.solid_dots) * g.dot_mm
    rows = []
    for p in man["patches"]:
        states, planes = patch_arrays(npz, p, g.pattern_dots)
        rect = (p["x_mm"], p["y_mm"], p["x_mm"] + pw, p["y_mm"] + ph)
        try:
            white = local_white(scan, A, rect, rects, gwhite)
            rows.append(read_patch(scan, A, p, states, planes, g, white))
        except ValueError as exc:
            print(f"  patch {p['id']}: skipped ({exc})")
    classify_all(rows)
    head, lines = csv_table(rows)
    with open(out / f"{tag}-patches.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(head)
        w.writerows(lines)
    n_nom = sum(1 for r in rows if not r["reg_ok"])
    shift_max = max((abs(r["reg_dx_mm"]) + abs(r["reg_dy_mm"]) for r in rows), default=0.0)
    print(f"\n{len(rows)} patches read; registration fell back to nominal on {n_nom}; "
          f"|reg shift| max {shift_max:.3f} mm")
    cfgs = config_table(rows)
    comps = comparisons(cfgs)
    rank = print_report(cfgs, comps, man.get("arms"))
    fams, offs = family_table(rows), offset_table(rows)
    print_pose_report(fams, offs, rows)
    for r in rows:
        for k in ("_X", "_X1", "_y"):
            r.pop(k)
    summary = {"tag": tag, "scan": str(args.scan), "manifest": str(args.manifest),
               "patterns": str(patterns_path(mpath, man, args.patterns)), "job_sha256": man.get("sha256"),
               "job_bytes": man.get("bytes"), "fit": fit, "page_white": gwhite.tolist(),
               "n_patches_read": len(rows), "n_reg_nominal": n_nom,
               "classifier": "nearest mean in RGB (Euclidean); loo = leave-one-out on the patch itself; "
                             "cross = means from all cells of the other replicates of (arm, fraction, "
                             "method, neutral)",
               "plane_channels": {"C": "R", "M": "G", "Y": "B", "K": "max(R,G,B)"},
               "plane_rule": "C/M/Y planes leave out cells with any K ink; hard_err at the midpoint, "
                             "hard_err_best at the best threshold",
               "pose": "per plane: own dot mask vs own channel density (C R, M G, Y B, K max), "
                       f"+/- {PLANE_SEARCH_PX} px around the OR-ed pose, other planes unmixed by least "
                       "squares; R sampled at C's pose, G at M's, B at Y's; the K plane statistic at K's "
                       "pose; *_singlepose = every channel at the OR-ed pose (the previous readout)",
               "families": fams, "offsets_vs_C": offs,
               "configs": cfgs, "comparisons": comps, "ranking": rank, "patches": rows}
    (out / f"{tag}-summary.json").write_text(json.dumps(jsonable(summary), indent=1))
    print(f"\nwrote {out / (tag + '-patches.csv')} and {out / (tag + '-summary.json')}")


if __name__ == "__main__":
    main()

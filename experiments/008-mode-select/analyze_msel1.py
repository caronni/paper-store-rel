#!/usr/bin/env python
"""analyze_msel1 — MSEL-1 mode-selection analyzer (experiment 008).

Scores the MSEL-1 portfolio from 1200-dpi scans of the two pages and emits
the MODE RECOMMENDATION table from the PRE-REGISTERED decision rules R1-R7
in experiments/008-mode-select.md — the rules were written BEFORE this file;
this file implements exactly them (the constants below mirror the .md).

Pipeline per scan: cal_core registration (chiral corner marks + plus
lattice, exp 002 machinery) -> per-field GT-template phase lock
(cc.patch_view) -> GT-ink-quantile threshold decode (the 007.6 median-rule
floor bug is avoided by construction). Footing of every K/CMY number:
(marks-affine + per-field phase lock, labeled-GT scoring) = "discovery
grade"; A-track MI is a within-field checker-split QDA (mildly
fold-optimistic vs cross-page, Δ≈0.03 b/cell per 004.0).

Blocks scored: machine strips (self-ID + CRC), K portfolio c2..c6 + RLL
i2w3 at all positions/pages, A3/A4 state fields (color scan), per-plane
isolated c3 minis, crosstalk solids (mono gate + Y-health gate), emission
probe pair P0/P3 (overlap preserved-vs-knockout per path), screen-FFT hunt
on the A3 field (reuses analyze_disc1._fft_peaks, M281-calibrated band),
scanner-adequacy block (strips CRC, known c3/c2 fields, 2-on/2-off
gratings, JPEG blockiness canary + quiet-zone noise floor).

Also hosts the SIM HARNESS (sim_k_scan / sim_color_scan / fake_scan): the
M0 gate in tests/test_msel1.py drives the same scoring + decision code on
measured-simulator output (geometry=False, sim-genie footing) and requires
the pre-registered recommendation for M281 defaults.

Usage:
  analyze_msel1.py --grey1 p1-grey.png [--color1 p1-color.png]
                   [--grey2 p2-grey.png] [--color2 p2-color.png]
                   [--json out.json] [--manifest path]

Deterministic; no RNG anywhere.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_erosion, gaussian_filter

_HERE = Path(__file__).resolve().parent
_EXP002 = _HERE.parent / "002-calibration-page"
_EXP007 = _HERE.parent / "007-office-disc"
for _p in (str(_HERE), str(_EXP002), str(_EXP007)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import analyze_disc1 as ad  # noqa: E402  (_fft_peaks/_profile_contrast, 007.6-calibrated)
import cal_core as cc  # noqa: E402       (exp002 registration/resampling foundation)
import stripdec  # noqa: E402             (machine-strip reference decoder)

BUILD = _HERE / "build"
MANIFEST_PATH = BUILD / "msel1_manifest.json"

# ---------------------------------------------------------------------------
# PRE-REGISTERED decision constants (mirror experiments/008-mode-select.md;
# changing any of these is a logged .md amendment, not a tuning knob)
# ---------------------------------------------------------------------------
TIER_SOLID = 0.01          # solid < 1% raw hard BER
TIER_MARGINAL = 0.08       # marginal 1-8%; fragile 8-20%; dead >= 20%
TIER_DEAD = 0.20
ROBUST_BER = TIER_SOLID / 2.0    # R2: 2x margin under the solid boundary
DENSE_CEILING = TIER_MARGINAL    # R3: exclude the fragile/day-fragile tier
ADEQ_C3_BER = 0.05         # adequacy: solid-class decode
ADEQ_C2_BER = 0.18         # adequacy: marginal-class decode
CONTRAST_MIN = 0.20        # adequacy: 2-on/2-off sampling check
BLOCKINESS_MAX = 1.25      # adequacy: JPEG canary (007.2 measured 1.68)
NOISE_STD_MIN = 1.0        # adequacy: quiet-zone high-pass std, grey counts
NOISE_STD_SYNTH = 0.5      # below this: synthetic/processed scan -> indeterminate
MONO_SELECTIVITY = 0.10    # R5a: D_primary - mean(D_others) per C/M/Y solid
Y_HEALTH_RATIO = 0.5       # R5b: D_b(Y) >= 0.5 * D_r(C)
A3_MI_FLOOR = 1.0          # R5c: worst-position A3 MI b/cell
SCREEN_PEAK_REL = 300.0    # 007.6 band-median diagnostic (kept per peak)
SCREEN_ANNULUS_REL = 50.0  # classifier: off-axis peak vs its radial annulus
PLANE_FALLBACK_BER = 0.10  # R5d: per-plane isolated c3 minis
RATE_SAFETY = 0.85         # R6: provisional rate discount

FOOTING = ("marks-affine + per-field GT phase lock (discovery grade)",
           "labeled(GT); A-track MI = within-field checker-split QDA")
PROVISIONAL = ("PROVISIONAL-SINGLE-SHEET: final rate ladders on multi-sheet "
               "minima (007.9); within-page position spread is the built-in "
               "variance proxy, not a substitute")


def h2(p: float) -> float:
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return float(-p * math.log2(p) - (1 - p) * math.log2(1 - p))


def cells_per_mm2(cell_dots: int) -> float:
    return (600.0 / 25.4 / cell_dots) ** 2


# ---------------------------------------------------------------------------
# manifest handling
# ---------------------------------------------------------------------------

def load_manifest(path: str | Path = MANIFEST_PATH) -> dict:
    return cc.load_manifest(path)


def page_mf(mf: dict, page: int) -> dict:
    """Manifest restricted to one page (all-600-grid; _base_dir preserved)."""
    m2 = {k: v for k, v in mf.items()
          if k not in ("patches", "infrastructure", "labels")}
    m2["patches"] = [e for e in mf["patches"] if e.get("page", 1) == page]
    m2["infrastructure"] = [e for e in mf["infrastructure"]
                            if e.get("page", 1) == page]
    m2["labels"] = [lb for lb in mf["labels"] if lb.get("page", 1) == page]
    return m2


def entries_where(mf: dict, **want) -> list[dict]:
    out = []
    for e in mf["patches"]:
        p = e.get("params", {})
        if all(e.get(k) == v or p.get(k) == v for k, v in want.items()):
            out.append(e)
    return out


# ---------------------------------------------------------------------------
# field scorers (R1 footing)
# ---------------------------------------------------------------------------

def score_pn(scan: dict, e: dict) -> dict:
    """Cell BER of a PN field: GT-template phase lock + GT-ink-quantile
    threshold (NOT the median rule — 007.6 floor bug) + null control."""
    cell = e["params"]["cell_dots"]
    gt = cc.load_gt(e)
    view = cc.patch_view(scan, e, margin_dots=8, sub=2, local="gt")
    m = cc.cell_means(view)
    gtc = gt[::cell, ::cell]
    assert m.shape == gtc.shape, (e["name"], m.shape, gtc.shape)
    thr = float(np.quantile(m, float(gtc.mean())))
    bits = (m < thr).astype(np.uint8)          # ink dark -> 1
    r = cc.ber_with_null(bits, gtc)
    return {"name": e["name"], "cell_dots": cell,
            "position": e["params"].get("position"),
            "page": e.get("page", 1), "ber": r["ber"],
            "n_cells": r["n_cells"], "ber_null": r["ber_null"],
            "null_ok": r["null_ok"], "lock_q": view.local_quality,
            "locked": view.local_locked}


def score_rll(scan: dict, e: dict) -> dict:
    """Dot BER of the RLL field + the 003.0 rate proxy
    sampler_entropy x (1 - H2(dot BER)) b/dot (analyze_modprobe formula)."""
    gt = cc.load_gt(e)
    view = cc.patch_view(scan, e, margin_dots=8, sub=2, local="gt")
    m = cc.cell_means(view, cell_dots=1)
    assert m.shape == gt.shape, (e["name"], m.shape, gt.shape)
    thr = float(np.quantile(m, float(gt.mean())))
    bits = (m < thr).astype(np.uint8)
    r = cc.ber_with_null(bits, gt)
    # Constrained fields are run-correlated: the shifted-GT null is NOT 0.5
    # but the field's own lag-8 decorrelation (analyze_modprobe "null (exp)"
    # idiom) — compare the measured null against that expectation instead.
    exp_null = float((gt.astype(bool)
                      != np.roll(gt.astype(bool), 8, axis=1)).mean())
    null_ok = bool(abs(r["ber_null"] - exp_null) <= 0.02)
    hs = float(e["params"]["sampler_entropy_bits_per_dot"])
    proxy = hs * (1.0 - h2(r["ber"]))
    return {"name": e["name"], "position": e["params"].get("position"),
            "page": e.get("page", 1), "ber_dots": r["ber"],
            "n_dots": r["n_cells"], "ber_null": r["ber_null"],
            "ber_null_expected": exp_null,
            "null_ok": null_ok, "sampler_entropy_b_dot": hs,
            "proxy_b_per_dot": proxy,
            "proxy_b_per_mm2": proxy * (600.0 / 25.4) ** 2,
            "lock_q": view.local_quality, "locked": view.local_locked}


def _qda_confusion(feats: np.ndarray, labels: np.ndarray, n_states: int
                   ) -> tuple[np.ndarray, float]:
    """Within-field checker-split QDA: train on (iy+ix) even cells, test on
    odd. feats (ny, nx, d) float; labels (ny, nx) int. Returns (confusion
    counts test-set [true, pred], accuracy)."""
    ny, nx, d = feats.shape
    iy, ix = np.mgrid[0:ny, 0:nx]
    train = ((iy + ix) % 2 == 0).ravel()
    X = feats.reshape(-1, d).astype(np.float64)
    y = labels.ravel().astype(int)
    mus, covs_i, logdets = [], [], []
    for s in range(n_states):
        Xs = X[train & (y == s)]
        mu = Xs.mean(axis=0)
        cov = np.cov(Xs.T) + np.eye(d) * (1e-4 * float(np.trace(np.cov(Xs.T)))
                                          / d + 1e-9)
        mus.append(mu)
        covs_i.append(np.linalg.inv(cov))
        logdets.append(np.linalg.slogdet(cov)[1])
    Xt = X[~train]
    yt = y[~train]
    scores = np.empty((len(Xt), n_states))
    for s in range(n_states):
        dxy = Xt - mus[s]
        scores[:, s] = -0.5 * (np.einsum("ij,jk,ik->i", dxy, covs_i[s], dxy)
                               + logdets[s])
    pred = np.argmax(scores, axis=1)
    conf = np.zeros((n_states, n_states), np.int64)
    np.add.at(conf, (yt, pred), 1)
    return conf, float((pred == yt).mean())


def _mi_from_confusion(conf: np.ndarray) -> float:
    j = conf.astype(np.float64) / max(conf.sum(), 1)
    px = j.sum(axis=1, keepdims=True)
    py = j.sum(axis=0, keepdims=True)
    nz = j > 0
    return float((j[nz] * np.log2(j[nz] / (px @ py)[nz])).sum())


def cell_core_density(view: "cc.PatchView", cell_dots: int, channel: str
                      ) -> np.ndarray:
    """Per-cell CORE density feature: trim cp//3 px per side (the PSF/screen-
    blurred cell border), mean the core, -log10 to density domain (the
    LAYERS.md CellFeatures currency; QDA classes are closer to Gaussian
    there and the border trim buys ~+0.15 b/cell on the simulated screened
    channel vs whole-cell means)."""
    a = view.crop(channel)
    cp = cell_dots * view.sub
    t = max(1, cp // 3)
    ny, nx = a.shape[0] // cp, a.shape[1] // cp
    b = a[: ny * cp, : nx * cp].reshape(ny, cp, nx, cp)
    core = b[:, t: cp - t, :, t: cp - t].mean(axis=(1, 3))
    return -np.log10(np.clip(core, 3.0, None) / 255.0)


def score_state(scan: dict, mf: dict, comp_name: str) -> dict | None:
    """A3/A4 state-field MI b/cell from per-cell r,g,b core density
    features (rgb-only per 007.8-C2), within-field checker-split QDA.
    None on grey scans."""
    if scan["kind"] != "color":
        return None
    planes = [e for e in mf["patches"] if e.get("composite_of") == comp_name]
    e0 = planes[0]
    cell = e0["params"]["cell_dots"]
    n_states = e0["params"]["n_states"]
    st = cc.load_gt_named(e0["params"]["states_gt"], e0["_base_dir"])
    union = np.zeros((e0["h_dots"], e0["w_dots"]), np.uint8)
    for e in planes:
        union |= cc.load_gt(e)
    view = cc.patch_view(scan, e0, margin_dots=8, sub=2,
                         template_dots=union, channel="grey")
    feats = np.stack([cell_core_density(view, cell, ch)
                      for ch in ("r", "g", "b")], axis=-1)
    assert feats.shape[:2] == st.shape, (comp_name, feats.shape, st.shape)
    conf, acc = _qda_confusion(feats, st, n_states)
    mi = _mi_from_confusion(conf)
    return {"name": comp_name, "position": e0["params"].get("position"),
            "cell_dots": cell, "n_states": n_states, "acc": acc,
            "mi_b_cell": mi, "mi_b_mm2": mi * cells_per_mm2(cell),
            "n_test_cells": int(conf.sum()),
            "lock_q": view.local_quality, "locked": view.local_locked,
            "method": "within-field checker-split QDA on rgb per-cell core "
                      "density features (fold-optimism vs cross-page "
                      "≈ +0.03 b/cell, 004.0)"}


# ---------------------------------------------------------------------------
# solids / emission / screen
# ---------------------------------------------------------------------------

def _patch_median(scan: dict, e: dict, channel: str,
                  template: np.ndarray | None = None) -> float:
    view = cc.patch_view(scan, e, margin_dots=6, sub=2,
                         template_dots=template,
                         local="none" if template is None else "auto",
                         channel="grey")
    return float(np.median(view.crop(channel)))


def score_solids(scan: dict, mf: dict) -> dict | None:
    """Channel densities of the crosstalk-row solids vs the paper gap."""
    if scan["kind"] != "color":
        return None
    e_paper = cc.entry(mf, "xr/paper")
    white = {ch: _patch_median(scan, e_paper, ch) for ch in ("r", "g", "b")}
    out: dict = {"white": white, "density": {}}
    ones = None
    for nm in ("xr/clean_C", "xr/clean_M", "xr/clean_Y", "xr/clean_K",
               "xr/cmyk_CM", "xr/cmyk_CY", "xr/cmyk_MY"):
        e = cc.entry(mf, nm)
        if ones is None or ones.shape != (e["h_dots"], e["w_dots"]):
            ones = np.ones((e["h_dots"], e["w_dots"]), np.float32)
        out["density"][nm] = {
            ch: max(0.0, math.log10(max(white[ch], 1e-3)
                                    / max(_patch_median(scan, e, ch, ones),
                                          1e-3)))
            for ch in ("r", "g", "b")}
    return out


def solid_gates(density: dict[str, dict[str, float]]) -> dict:
    """R5a mono gate + R5b Y-health gate from the clean-solid densities."""
    prim = {"C": "r", "M": "g", "Y": "b"}
    sel = {}
    for p, ch in prim.items():
        d = density[f"xr/clean_{p}"]
        others = [d[c] for c in ("r", "g", "b") if c != ch]
        sel[p] = float(d[ch] - np.mean(others))
    mono = all(v < MONO_SELECTIVITY for v in sel.values())
    d_yb = density["xr/clean_Y"]["b"]
    d_cr = density["xr/clean_C"]["r"]
    y_ratio = d_yb / max(d_cr, 1e-6)
    return {"selectivity": sel, "mono_engine": bool(mono),
            "y_health_ratio": float(y_ratio),
            "y_healthy": bool(y_ratio >= Y_HEALTH_RATIO),
            "rule": f"mono iff all selectivity < {MONO_SELECTIVITY}; "
                    f"Y healthy iff D_b(Y) >= {Y_HEALTH_RATIO} x D_r(C)"}


def score_emission(scan: dict, mf: dict) -> dict | None:
    """P0 (cmyk image) vs P3 (masks+overprint+OPM) overlapping C+M solids:
    preserved-vs-knockout index per path (002.1 discriminator).

    Index = (D_r(overlap) - D_r(M-only)) / (D_r(C-only) - D_r(M-only)):
    1 = C survives under M in the overlap (preserved), 0 = knocked out."""
    if scan["kind"] != "color":
        return None
    e_paper = cc.entry(mf, "xr/paper")
    white_r = _patch_median(scan, e_paper, "r")
    out: dict = {}
    for path, comp in (("P0_cmyk", "em/p0_cm"), ("P3_masks_opm", "em/p3_cm")):
        planes = {e["planes"][0]: e for e in mf["patches"]
                  if e.get("composite_of") == comp}
        gc, gm = cc.load_gt(planes["C"]), cc.load_gt(planes["M"])
        e0 = planes["C"]
        union = (gc | gm).astype(np.float32)
        view = cc.patch_view(scan, e0, margin_dots=6, sub=2,
                             template_dots=union, channel="grey")
        img_r = view.crop("r")
        dens = {}
        for zone, mask in (("c_only", (gc == 1) & (gm == 0)),
                           ("overlap", (gc == 1) & (gm == 1)),
                           ("m_only", (gc == 0) & (gm == 1))):
            core = binary_erosion(mask, iterations=6)
            px = np.kron(core, np.ones((2, 2), bool))
            med = float(np.median(img_r[px]))
            dens[zone] = max(0.0, math.log10(max(white_r, 1e-3)
                                             / max(med, 1e-3)))
        span = dens["c_only"] - dens["m_only"]
        idx = (dens["overlap"] - dens["m_only"]) / span if abs(span) > 0.02 \
            else float("nan")
        verdict = ("indeterminate" if not np.isfinite(idx) else
                   "preserved" if idx > 0.7 else
                   "knockout" if idx < 0.3 else "partial")
        out[path] = {"zone_density_r": dens, "preserved_index": idx,
                     "verdict": verdict}
    return out


def _fft_screen_peaks(img: np.ndarray, sub_px: int, dpi: int, *,
                      n_peaks: int = 4, lpi_lo: float = 110.0,
                      lpi_hi: float = 320.0, exclude_axis_deg: float = 7.0
                      ) -> list[dict]:
    """analyze_disc1._fft_peaks band/off-axis machinery + ANNULUS-relative
    normalization: peak power vs the median of its own +-8-lpi radial
    annulus. Band-median normalization (the 007.6 diagnostic) is kept per
    peak, but the classifier uses the annulus ratio — a radially-colored
    noise floor (sim mottle/PSF, scanner rolloff) inflates the band-median
    ratio without any periodic component; the annulus ratio does not."""
    from scipy.ndimage import maximum_filter
    a = img.astype(np.float64)
    a -= a.mean()
    wy = np.hanning(a.shape[0])[:, None]
    wx = np.hanning(a.shape[1])[None, :]
    P = np.abs(np.fft.fftshift(np.fft.fft2(a * wy * wx))) ** 2
    pitch_mm = 25.4 / (dpi * sub_px)
    fy = np.fft.fftshift(np.fft.fftfreq(a.shape[0], d=pitch_mm))
    fx = np.fft.fftshift(np.fft.fftfreq(a.shape[1], d=pitch_mm))
    FX, FY = np.meshgrid(fx, fy)
    R = np.hypot(FX, FY) * 25.4          # lpi
    ang = np.degrees(np.arctan2(FY, FX)) % 90.0
    off_axis = np.minimum(ang, 90.0 - ang) > exclude_axis_deg
    band = (R >= lpi_lo) & (R <= lpi_hi) & (FY >= 0) & off_axis
    loc = (P == maximum_filter(P, size=9)) & band
    idx = np.argsort(P[loc])[::-1][:n_peaks]
    ys, xs = np.nonzero(loc)
    band_med = float(np.median(P[band])) + 1e-12
    out = []
    for i in idx:
        y, x = ys[i], xs[i]
        ann = band & (np.abs(R - R[y, x]) <= 8.0)
        ann_med = float(np.median(P[ann])) + 1e-12
        out.append({"lpi": float(R[y, x]),
                    "angle_deg": float(math.degrees(math.atan2(FY[y, x],
                                                               FX[y, x]))),
                    "power_rel_band_median": float(P[y, x] / band_med),
                    "power_rel_annulus_median": float(P[y, x] / ann_med)})
    return out


def screen_hunt(scan: dict, mf: dict, comp_name: str) -> dict | None:
    """Off-axis screen-FFT hunt on the A3 field's C plane (r channel).
    Band + off-axis exclusion from the 007.6 M281-calibrated hunt
    (analyze_disc1); classifier = annulus-relative peak power (validated
    both ways on the measured simulator; first real MSEL run should
    confirm against the 007.6 band-median record — see .md limitations)."""
    if scan["kind"] != "color":
        return None
    planes = [e for e in mf["patches"] if e.get("composite_of") == comp_name]
    e0 = planes[0]
    union = np.zeros((e0["h_dots"], e0["w_dots"]), np.uint8)
    for e in planes:
        union |= cc.load_gt(e)
    view = cc.patch_view(scan, e0, margin_dots=8, sub=2,
                         template_dots=union, channel="grey")
    peaks = _fft_screen_peaks(view.crop("r"), 2, 600)
    top = peaks[0]["power_rel_annulus_median"] if peaks else 0.0
    return {"field": comp_name, "peaks": peaks,
            "screened": bool(top > SCREEN_ANNULUS_REL),
            "threshold_rel_annulus": SCREEN_ANNULUS_REL,
            "band_median_diagnostic_threshold": SCREEN_PEAK_REL}


# ---------------------------------------------------------------------------
# scanner adequacy (pre-registered criteria table in the .md)
# ---------------------------------------------------------------------------

def _blockiness(img: np.ndarray) -> float:
    """8-px block-boundary energy ratio (both axes, worst): JPEG signature."""
    out = 1.0
    for a in (img, img.T):
        d = np.abs(np.diff(a.astype(np.float64), axis=1))
        n = (d.shape[1] // 8) * 8
        if n < 16:
            continue
        d = d[:, :n]
        onb = d[:, 7::8].mean()
        offb = (d.sum() - d[:, 7::8].sum()) / max(d.size - d[:, 7::8].size, 1)
        if offb > 1e-6:
            out = max(out, float(onb / offb))
    return out


def _raw_crop(scan: dict, e: dict, inset_dots: float = 2.0) -> np.ndarray:
    """Native-scan-pixel crop of an entry's rect (blockiness lives in scan
    pixel space — resampling would smear it)."""
    x0, y0 = e["x_dots"] + inset_dots, e["y_dots"] + inset_dots
    x1 = e["x_dots"] + e["w_dots"] - inset_dots
    y1 = e["y_dots"] + e["h_dots"] - inset_dots
    pts = cc.affine_apply(scan["affine"],
                          np.array([[x0, y0], [x1, y0], [x0, y1], [x1, y1]]))
    g = scan["grey"]
    xa, ya = pts[:, 0], pts[:, 1]
    return g[int(max(0, ya.min())): int(min(g.shape[0], ya.max())),
             int(max(0, xa.min())): int(min(g.shape[1], xa.max()))]


def score_adequacy(scan: dict, mf: dict) -> dict:
    """The pre-registered scanner-adequacy criteria (page 1 grey scan)."""
    img8 = np.clip(scan["grey"], 0, 255).astype(np.uint8)
    strips = stripdec.decode_image(img8)
    n_crc = sum(1 for s in strips if s["crc_ok"])
    c3 = score_pn(scan, cc.entry(mf, "adq/k_c3"))
    c2 = score_pn(scan, cc.entry(mf, "adq/k_c2"))
    gr = {}
    for o in ("h", "v"):
        e = cc.entry(mf, f"adq/g2{o}")
        view = cc.patch_view(scan, e, margin_dots=4, sub=2, local="none")
        img = view.crop("grey")
        white = float(np.percentile(img, 97))
        black = float(np.percentile(img, 3))
        gr[o] = ad._profile_contrast(img, e["params"]["orientation"],
                                     2.0 * e["params"]["pitch_dots"] * 2,
                                     white, black)
    blk = _blockiness(_raw_crop(scan, cc.entry(mf, "adq/entropy")))
    qz = _raw_crop(scan, cc.entry(mf, "quiet_zone"), inset_dots=6.0)
    noise = float((qz - gaussian_filter(qz.astype(np.float64), 4.0)).std())
    if noise < NOISE_STD_SYNTH:
        comp = "indeterminate"
    else:
        comp = "pass" if (blk < BLOCKINESS_MAX and noise >= NOISE_STD_MIN) \
            else "fail"
    checks = {
        "strips_crc": {"n_crc_ok": n_crc, "n_found": len(strips),
                       "pass": bool(n_crc >= 1)},
        "solid_class": {"ber": c3["ber"], "pass": bool(c3["ber"] < ADEQ_C3_BER)},
        "marginal_class": {"ber": c2["ber"],
                           "pass": bool(c2["ber"] < ADEQ_C2_BER)},
        "sampling": {"contrast_h": gr["h"], "contrast_v": gr["v"],
                     "pass": bool(min(gr.values()) >= CONTRAST_MIN)},
        "compression": {"blockiness": blk, "quiet_noise_std": noise,
                        "verdict": comp},
    }
    solid_ok = (checks["strips_crc"]["pass"] and checks["solid_class"]["pass"]
                and checks["sampling"]["pass"])
    c2_ok = solid_ok and checks["marginal_class"]["pass"] and comp == "pass"
    return {"checks": checks,
            "adequate_solid_class_modes": bool(solid_ok),
            "adequate_c2_class_modes": bool(c2_ok),
            "note": "compressed-path scans: hard/global detection only, "
                    "expect ~+6 pp at c2-class (007.2)"}


# ---------------------------------------------------------------------------
# decision rules R2-R6 (pre-registered; see the .md)
# ---------------------------------------------------------------------------

def decide(k_rows: list[dict], rll_rows: list[dict], a_rows: list[dict],
           iso_rows: list[dict], solid_density: dict | None,
           emission: dict | None, screen: dict | None,
           adequacy: dict | None, color_available: bool) -> dict:
    out: dict = {"footing": FOOTING, "provisional": PROVISIONAL}

    # ---- R1/R2/R3: K table on worst-position numbers ----------------------
    k_table: dict[int, dict] = {}
    for r in k_rows:
        c = r["cell_dots"]
        k_table.setdefault(c, {"cell_dots": c, "positions": []})
        k_table[c]["positions"].append(
            {"name": r["name"], "ber": r["ber"], "locked": r["locked"]})
    for c, t in sorted(k_table.items()):
        bers = [p["ber"] for p in t["positions"]]
        w = max(bers)
        t.update({"worst_ber": w, "median_ber": float(np.median(bers)),
                  "n_positions": len(bers),
                  "tier": ("solid" if w < TIER_SOLID else
                           "marginal" if w < TIER_MARGINAL else
                           "fragile" if w < TIER_DEAD else "dead"),
                  "proxy_b_cell": 1.0 - h2(w),
                  "proxy_b_mm2": (1.0 - h2(w)) * cells_per_mm2(c),
                  "rate_suggest_b_cell": RATE_SAFETY * (1.0 - h2(w))})
    out["k_table"] = [k_table[c] for c in sorted(k_table)]

    robust = None
    for c in sorted(k_table, reverse=True):            # largest cell first
        if k_table[c]["worst_ber"] < ROBUST_BER:
            robust = {"cell_dots": c, "worst_ber": k_table[c]["worst_ber"],
                      "margin": "full (>=2x under the 1% solid boundary)",
                      "rate_suggest_b_cell":
                          k_table[c]["rate_suggest_b_cell"]}
            break
    if robust is None:
        for c in sorted(k_table, reverse=True):
            if k_table[c]["worst_ber"] < TIER_SOLID:
                robust = {"cell_dots": c,
                          "worst_ber": k_table[c]["worst_ber"],
                          "margin": "REDUCED (<2x under the 1% boundary)",
                          "rate_suggest_b_cell":
                              k_table[c]["rate_suggest_b_cell"]}
                break
    out["robust_k"] = robust or {"verdict": "no robust K mode in portfolio — "
                                            "extend the ladder or reject the "
                                            "engine"}

    dense_c = [c for c in k_table if k_table[c]["worst_ber"] < DENSE_CEILING]
    if dense_c:
        best = max(dense_c, key=lambda c: k_table[c]["proxy_b_mm2"])
        out["dense_k"] = {"cell_dots": best,
                          "worst_ber": k_table[best]["worst_ber"],
                          "proxy_b_mm2": k_table[best]["proxy_b_mm2"],
                          "rate_suggest_b_cell":
                              k_table[best]["rate_suggest_b_cell"]}
    else:
        out["dense_k"] = {"verdict": "no cell below the 8% ceiling"}
    if 2 in k_table and TIER_MARGINAL <= k_table[2]["worst_ber"] < TIER_DEAD:
        out["c2_upside_note"] = (
            f"c2 excluded at {100 * k_table[2]['worst_ber']:.1f}% "
            f"(fragile tier, day-fragile class per 004.0); B1-class context "
            f"detection + LDPC might recover it — re-measure via the v4 "
            f"path + a second-day sheet before using")

    # ---- R4: RLL / B2 anchor ----------------------------------------------
    if rll_rows:
        w = max(r["ber_dots"] for r in rll_rows)
        hs = min(r["sampler_entropy_b_dot"] for r in rll_rows)
        proxy = hs * (1.0 - h2(w))
        out["rll_b2_anchor"] = {
            "worst_ber_dots": w,
            "median_ber_dots": float(np.median([r["ber_dots"]
                                                for r in rll_rows])),
            "n_positions": len(rll_rows),
            "proxy_b_per_dot": proxy,
            "proxy_b_per_mm2": proxy * (600.0 / 25.4) ** 2,
            "cross_engine_band_b_mm2": [82.0, 86.0],
            "in_band": bool(82.0 * 0.8 <= proxy * (600.0 / 25.4) ** 2
                            <= 86.0 * 1.2),
        }

    # ---- R5: CMY chain -----------------------------------------------------
    if not color_available:
        out["cmy"] = {"verdict": "needs color scan"}
    else:
        gates = solid_gates(solid_density["density"]) if solid_density else None
        cmy: dict = {"gates": gates, "emission": emission, "screen": screen}
        a3 = [a for a in a_rows if a and a["n_states"] == 7]
        if gates and gates["mono_engine"]:
            cmy["verdict"] = "mono engine / CMY unusable"
        elif a3 and gates and gates["y_healthy"] and \
                min(a["mi_b_cell"] for a in a3) >= A3_MI_FLOOR:
            wmi = min(a["mi_b_cell"] for a in a3)
            cls = ("screened_composite" if screen and screen["screened"]
                   else "unscreened_composite")
            cmy["verdict"] = "A3_7st_c3"
            cmy["channel_class"] = cls
            cmy["worst_position_mi_b_cell"] = wmi
            cmy["worst_position_mi_b_mm2"] = wmi * cells_per_mm2(3)
            cmy["rate_suggest_b_cell"] = RATE_SAFETY * wmi
            a4 = [a for a in a_rows if a and a["n_states"] == 8]
            if a4:
                cmy["a4_comparison_mi_b_mm2"] = min(
                    a["mi_b_cell"] for a in a4) * cells_per_mm2(4)
        else:
            ok_planes = {}
            for p in ("C", "M", "Y"):
                rows = [r for r in iso_rows if r["name"].endswith(f"iso_{p}_c3")]
                if rows:
                    ok_planes[p] = max(r["ber"] for r in rows)
            good = [p for p, b in ok_planes.items()
                    if b < PLANE_FALLBACK_BER]
            if len(good) >= 2:
                cmy["verdict"] = "per_plane_clean_mask_c3"
                cmy["plane_worst_ber"] = ok_planes
                cmy["usable_planes"] = good
                cmy["rate_suggest_b_cell_per_plane"] = {
                    p: RATE_SAFETY * (1.0 - h2(b))
                    for p, b in ok_planes.items() if p in good}
            else:
                cmy["verdict"] = "CMY unusable on this engine/scanner path"
        if a3:
            cmy["a3_positions"] = [{"name": a["name"], "mi": a["mi_b_cell"],
                                    "acc": a["acc"]} for a in a3]
        out["cmy"] = cmy

    out["scanner_adequacy"] = adequacy
    return out


# ---------------------------------------------------------------------------
# SIM HARNESS (M0 gate; sim-genie footing, geometry=False)
# ---------------------------------------------------------------------------

def fake_scan(channels: dict[str, np.ndarray], e: dict, pad_dots: int,
              kind: str) -> dict:
    """Scan dict for a simulated crop of one entry: crop covers the entry
    rect plus pad_dots on each side at 2 px/dot (identity-x2 affine)."""
    grey = channels["grey"]
    white, black, thresh = cc.levels(grey)
    return {"path": "<sim>", "sha256": None, "kind": kind, "grey": grey,
            "channels": channels, "white": white, "black": black,
            "thresh": thresh, "scan_dpi": 1200, "hw_dpi": 600,
            "px_per_dot": 2.0, "orientation": None,
            "affine": np.array([2.0, 0.0, -2.0 * (e["x_dots"] - pad_dots),
                                0.0, 2.0, -2.0 * (e["y_dots"] - pad_dots)]),
            "registration": None, "manifest": None}


def sim_k_scan(e: dict, seed: int, pad_dots: int = 12) -> dict:
    """One K entry through the measured M281 print+scan channel
    (geometry=False: the M0 plumbing footing, per test_e004 idiom)."""
    from paperholo.channel.simulator import ChannelParams, print_scan
    bits = np.pad(cc.load_gt(e), pad_dots)
    refl = print_scan(bits, ChannelParams(seed=seed, geometry=False))
    grey = np.clip(refl * 255.0, 0, 255).astype(np.float32)
    return fake_scan({"grey": grey}, e, pad_dots, "grey")


def sim_color_scan(plane_bits: dict[str, np.ndarray], e: dict, seed: int,
                   screened: bool, pad_dots: int = 12) -> dict:
    """A composite entry through the measured color channel: optional RIP
    rescreen per plane (M281_SCREENS), development + PSF -> ink coverage,
    measured crosstalk compose to r,g,b reflectance, then the scanner stage
    per channel with shared (null) geometry — one physical scan."""
    from paperholo.channel.simulator import (M281_PLANES, M281_SCREENS,
                                             ChannelParams, PrintedPlane,
                                             _develop, planes_to_rgb_refl,
                                             rescreen_plane, scan_plane)
    cov: dict[str, np.ndarray] = {}
    for p, bits in plane_bits.items():
        b = np.pad(bits, pad_dots)
        pl = M281_PLANES[p]
        if screened:
            # RIP re-screen: the screen is the ENGINE'S OWN rendering — the
            # dev-morphology gates (min-ink/white-fill) were measured for
            # FOREIGN 600-dpi mask bitmaps and would double-count here
            # (binary_opening kills the engine's screen dots). PSF only.
            lpi, ang = M281_SCREENS.get(p, (165.0, 14.0))
            ink = rescreen_plane(b, 600, lpi, ang).astype(np.float64)
        else:
            ink = _develop(b, pl)
        cov[p] = gaussian_filter(ink, (pl.psf_sigma_dots_y,
                                       pl.psf_sigma_dots_x))
    rgb = planes_to_rgb_refl(cov)
    h, w = rgb.shape[:2]
    channels: dict[str, np.ndarray] = {}
    for i, ch in enumerate("rgb"):
        printed = PrintedPlane(refl_dots=rgb[..., i], dpi=600,
                               wander_dy_of_y=np.zeros(h), y_scale_error=0.0,
                               reg_dy_of_y=np.zeros(h),
                               reg_dx_of_x=np.zeros(w))
        img = scan_plane(printed, ChannelParams(geometry=False,
                                                scan_seed=seed + i))
        channels[ch] = np.clip(img * 255.0, 0, 255).astype(np.float32)
    channels["grey"] = (0.299 * channels["r"] + 0.587 * channels["g"]
                        + 0.114 * channels["b"])
    return fake_scan(channels, e, pad_dots, "color")


# ---------------------------------------------------------------------------
# full-scan analysis + CLI
# ---------------------------------------------------------------------------

def analyze(scans: dict[str, dict | None], mf: dict) -> dict:
    """scans: {'p1_grey','p1_color','p2_grey','p2_color'} (registered scan
    dicts or None). K fields prefer the grey scan of their page (B-track
    grey preference, 004.0b); color blocks need the page-1 color scan."""
    rep: dict = {"jobid": mf["jobid"], "strips": {}}
    k_rows, rll_rows, iso_rows, a_rows = [], [], [], []
    for page in (1, 2):
        scan = scans.get(f"p{page}_grey") or scans.get(f"p{page}_color")
        if scan is None:
            continue
        pm = page_mf(mf, page)
        img8 = np.clip(scan["grey"], 0, 255).astype(np.uint8)
        rep["strips"][f"page{page}"] = [
            {"crc_ok": s["crc_ok"], "magic_ok": s["magic_ok"],
             "fields": s["fields"],
             "pg2": bool(s["payload"].startswith(b"PHCAL1;PG=2;"))}
            for s in stripdec.decode_image(img8)]
        for e in entries_where(pm, kind="pn_field", block="portfolio"):
            if e["planes"] == ["K"]:
                k_rows.append(score_pn(scan, e))
        for e in entries_where(pm, kind="constrained_field"):
            rll_rows.append(score_rll(scan, e))
    col = scans.get("p1_color")
    solids = emission = screen = None
    if col is not None:
        pm1 = page_mf(mf, 1)
        for e in entries_where(pm1, kind="pn_field", block="iso_plane"):
            iso_rows.append(score_pn(col, e))
        comp_names = sorted({e["composite_of"] for e in pm1["patches"]
                             if e.get("composite_of", "").endswith(("a3_c3",
                                                                    "a4_c4"))})
        for nm in comp_names:
            r = score_state(col, pm1, nm)
            if r is not None:
                a_rows.append(r)
        solids = score_solids(col, pm1)
        emission = score_emission(col, pm1)
        screen = screen_hunt(col, pm1, "pf1/a3_c3")
    adequacy = None
    s1 = scans.get("p1_grey") or scans.get("p1_color")
    if s1 is not None:
        adequacy = score_adequacy(s1, page_mf(mf, 1))
    rep["k_rows"] = k_rows
    rep["rll_rows"] = rll_rows
    rep["iso_rows"] = iso_rows
    rep["a_rows"] = a_rows
    rep["solids"] = solids
    rep["recommendation"] = decide(
        k_rows, rll_rows, a_rows, iso_rows, solids, emission, screen,
        adequacy, color_available=col is not None)
    return rep


def print_recommendation(rep: dict) -> None:
    rec = rep["recommendation"]
    print("=== MSEL-1 MODE RECOMMENDATION (provisional, single sheet) ===")
    for t in rec["k_table"]:
        print(f"  K c{t['cell_dots']}: worst {100 * t['worst_ber']:6.2f}%  "
              f"median {100 * t['median_ber']:6.2f}%  ({t['n_positions']} pos)"
              f"  tier={t['tier']:8s}  proxy {t['proxy_b_mm2']:6.1f} b/mm2")
    r = rec["robust_k"]
    if "cell_dots" in r:
        print(f"  ROBUST-K : c{r['cell_dots']}  worst "
              f"{100 * r['worst_ber']:.2f}%  rate<= "
              f"{r['rate_suggest_b_cell']:.3f} b/cell  [{r['margin']}]")
    else:
        print(f"  ROBUST-K : {r['verdict']}")
    d = rec["dense_k"]
    if "cell_dots" in d:
        print(f"  DENSE-K  : c{d['cell_dots']}  worst "
              f"{100 * d['worst_ber']:.2f}%  proxy {d['proxy_b_mm2']:.1f} "
              f"b/mm2  rate<= {d['rate_suggest_b_cell']:.3f} b/cell")
    if "c2_upside_note" in rec:
        print(f"  note: {rec['c2_upside_note']}")
    if "rll_b2_anchor" in rec:
        a = rec["rll_b2_anchor"]
        print(f"  RLL B2   : worst {100 * a['worst_ber_dots']:.2f}% dots  "
              f"proxy {a['proxy_b_per_mm2']:.1f} b/mm2  "
              f"(cross-engine band 82-86, in_band={a['in_band']})")
    c = rec["cmy"]
    print(f"  CMY      : {c['verdict']}"
          + (f"  class={c['channel_class']}  worst MI "
             f"{c['worst_position_mi_b_cell']:.3f} b/cell = "
             f"{c['worst_position_mi_b_mm2']:.1f} b/mm2  rate<= "
             f"{c['rate_suggest_b_cell']:.3f}"
             if c.get("verdict") == "A3_7st_c3" else ""))
    adq = rec.get("scanner_adequacy")
    if adq:
        print(f"  SCANNER  : solid-class adequate={adq['adequate_solid_class_modes']}"
              f"  c2-class adequate={adq['adequate_c2_class_modes']}")
    print(f"  footing  : {rec['footing'][0]}; {rec['footing'][1]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--grey1")
    ap.add_argument("--color1")
    ap.add_argument("--grey2")
    ap.add_argument("--color2")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--manifest", default=str(MANIFEST_PATH))
    args = ap.parse_args()
    mf = load_manifest(args.manifest)
    scans: dict[str, dict | None] = {}
    for key, path, page in (("p1_grey", args.grey1, 1),
                            ("p1_color", args.color1, 1),
                            ("p2_grey", args.grey2, 2),
                            ("p2_color", args.color2, 2)):
        if not path:
            scans[key] = None
            continue
        scan = cc.load_scan(path)
        cc.register(scan, page_mf(mf, page))
        scans[key] = scan
        reg = scan["registration"]
        print(f"{key}: registered, residual rms "
              f"{reg['residual_rms_dots']:.2f} dots, "
              f"{reg['n_landmarks_used']}/{reg['n_landmarks_total']} landmarks")
    if all(v is None for v in scans.values()):
        ap.error("no scans given")
    rep = analyze(scans, mf)
    print_recommendation(rep)
    if args.json_out:
        cc.save_report(rep, args.json_out)
        print(f"report -> {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

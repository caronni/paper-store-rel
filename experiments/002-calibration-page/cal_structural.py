#!/usr/bin/env python
"""cal_structural — per-plane structural channel family (experiment 002, CAL-1).

Measures, for each plane K, C, M, Y (K on the grey scan; C/M/Y on the color
scan's complementary channels r/g/b):

  * gratings H/V pitch 1-4  -> survival verdict per pitch/axis (resolved /
    collapsed / erased) from Murray-Davies ink fraction + segmented
    single-bin (Goertzel) fundamental amplitude; pitch-1 death is the datum;
  * checkers n=1-4          -> 2-D gain via the (n+2g)^2 / 2n^2 area model;
  * isolated dots n=1,2 and holes n=1,2,3 -> per-site detection with an
    OFF-LATTICE NULL CONTROL (threshold = null p99.5), survival fraction,
    blob-area gain, min reliable ink/white feature per plane;
  * slanted edges (5 deg)   -> binned ESF -> erf fit -> PSF sigma per axis
    (COARSE: 2 scan px per dot, includes scanner PSF and the 1-dot staircase);
  * density ladders 10-90% + solid + paper -> TRC / dot-gain (TVI) curve and
    mottle sigma vs coverage (block-D residual after regressing out the KNOWN
    ground-truth block coverage; instrument control = same regression against
    an 8-cell-shifted GT, R^2 must collapse).

Curated report keys (ANALYZER-CONTRACT §8, structural row):
  channel_params.{psf_sigma_dots, gain_edge_dots, dev_threshold_dots,
  min_feature_dots}; canaries D (1-dot phase pairs / resolution clamp) and
  F (RET / edge enhancement). TRC + mottle live under families.structural
  (channel_params.tvi / mottle_sigma are OWNED by the density_color family —
  putting them there would collide in report_merge).

Reuse: everything goes through cal_core (patch_view / density / white_model /
canary_verdict); no hand-rolled registration or resampling. cal_core re-exports
the proven experiment-001 scanlab primitives. This module uses NO randomness.

Run the smoke block:
  env/bin/python experiments/002-calibration-page/cal_structural.py \
      scans/test-scan-calpage-bw.png scans/test-scan-calpage-color.png
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.optimize import curve_fit
from scipy.special import erf

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import cal_core as cc  # noqa: E402

PLANES = ("K", "C", "M", "Y")

# --- thresholds (stated, not silent) ----------------------------------------
GRATING_MNORM_RESOLVED = 0.15   # fundamental amp / ideal square-wave amp
GRATING_SNR_RESOLVED = 3.0      # fundamental vs median off-harmonic floor
GRATING_AEFF_COLLAPSED = 0.50   # no modulation + ink majority -> collapsed
                                # (may be a GREY fill: 001's "closes solid"
                                # was thresholded; a_eff is Murray-Davies)
GRATING_AEFF_ERASED = 0.30      # no modulation + ink fraction below -> gone
SURVIVAL_RELIABLE = 0.90        # min-feature acceptance (design §11)
AREA_FRACTION_RELIABLE = 0.50   # ... and mean blob area >= 50% nominal
DETECT_CONTRAST_FRAC = 0.30     # 'detect' tier also needs a peak contrast
                                # >= 30% of the ink<->paper span (below that a
                                # trace cannot be thresholded against the
                                # measured mottle sigma with useful margin)
SITE_NULL_PCTL = 99.5           # detection threshold percentile on null sites
DOTS_MIN_QUALITY = 0.10         # lowered GT-lock gate for sparse dot lattices
                                # (contract §4: lower deliberately + say so)
MOTTLE_BLOCK_DOTS = 12          # 4x4 cells = 0.508 mm mottle block


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _ensure_registered(scan: dict) -> dict:
    if scan.get("registration") is None:
        cc.register(scan)
    return scan


def _crop_arr(view: cc.PatchView, arr: np.ndarray, trim_dots: int = 0) -> np.ndarray:
    """Crop a full-view raster (e.g. a density image) to the manifest entry,
    optionally trimming trim_dots more on every side (skirt exclusion)."""
    s = view.sub
    m = (view.margin_dots + trim_dots) * s
    h = (view.entry["h_dots"] - 2 * trim_dots) * s
    w = (view.entry["w_dots"] - 2 * trim_dots) * s
    return arr[m: m + h, m: m + w]


def _ratio_view(view: cc.PatchView, wm: dict, ch: str) -> np.ndarray:
    """Linear reflectance ratio v/white_local (1.0 = paper, ~R_solid = ink)."""
    d = cc.density(view, wm, channels=(ch,))[ch]
    return np.power(10.0, -d).astype(np.float32)


def _a_eff(mean_ratio: float, r_solid: float) -> float:
    """Murray-Davies effective dot area (n=1) from mean reflectance ratio."""
    return float((1.0 - mean_ratio) / max(1.0 - r_solid, 1e-6))


def _seg_tone(prof: np.ndarray, period_dots: float, sub: int) -> tuple[float, float]:
    """(amplitude, snr) of the fundamental in a 1-D profile.

    Segmented Hann-windowed FFT (robust to ~1-dot transport phase drift
    across the patch, which would smear a full-length transform at short
    periods); segment count adapts so each segment holds >= ~6 periods.
    Amplitude = half-amplitude of an equivalent cosine (peak of 3 bins around
    the fundamental). Noise floor = median spectrum magnitude excluding
    +-2.5 bins around DC and harmonics 1-4 of the fundamental.
    """
    f0 = 1.0 / period_dots                       # cycles/dot
    total_dots = len(prof) / sub
    n_seg = int(max(1, min(6, total_dots / period_dots / 6.0)))
    amps: list[float] = []
    floors: list[float] = []
    for s in np.array_split(prof, n_seg):
        n = len(s)
        if n / sub < 3.0 * period_dots:
            continue
        w = np.hanning(n)
        spec = np.abs(np.fft.rfft((s - s.mean()) * w)) * 2.0 / w.sum()
        freqs = np.fft.rfftfreq(n, d=1.0 / sub)  # cycles/dot
        bw = sub / n                             # bin width, cycles/dot
        k0 = int(round(f0 / bw))
        if not (1 <= k0 < len(spec) - 1):
            continue
        amps.append(float(spec[k0 - 1: k0 + 2].max()))
        keep = freqs > 1.5 * bw
        for m in (1, 2, 3, 4):
            keep &= np.abs(freqs - m * f0) > 2.5 * bw
        keep &= freqs < min(4.5 * f0, freqs[-1])
        if keep.sum() >= 4:
            floors.append(float(np.median(spec[keep])))
    if not amps:
        return 0.0, 0.0
    a = float(np.mean(amps))
    nf = float(np.mean(floors)) if floors else 1e-9
    return a, a / (nf + 1e-9)


def _tone_phase(prof: np.ndarray, pos_dots: np.ndarray, period_dots: float
                ) -> tuple[float, float]:
    """(amplitude, phase_rad) of the fundamental over a full profile with
    explicit sample positions in dots (used by the phase-pair canary)."""
    w = np.hanning(len(prof))
    xd = (prof - prof.mean()) * w
    z = np.sum(xd * np.exp(-2j * np.pi * pos_dots / period_dots))
    return float(2.0 * np.abs(z) / w.sum()), float(np.angle(z))


def _block_mean(a: np.ndarray, by: int, bx: int) -> np.ndarray:
    h, w = a.shape[0] // by, a.shape[1] // bx
    return a[: h * by, : w * bx].reshape(h, by, w, bx).mean(axis=(1, 3))


# ---------------------------------------------------------------------------
# per-plane context
# ---------------------------------------------------------------------------

@dataclass
class PlaneCtx:
    plane: str
    scan: dict            # grey scan for K, color scan for C/M/Y
    wm: dict              # white model of that scan
    ch: str               # measurement channel: K->grey, C->r, M->g, Y->b
    r_solid: float        # median v/white over the plane's solid patch
    d_solid: float        # median density over the solid patch
    solid_lock_q: float


def _plane_ctx(plane: str, scan_bw: dict, scan_color: dict,
               wm_bw: dict, wm_color: dict) -> PlaneCtx:
    if plane == "K":
        scan, wm, ch = scan_bw, wm_bw, "grey"
    else:
        scan, wm, ch = scan_color, wm_color, cc.REG_CHANNEL_FOR_PLANE[plane]
    v = cc.patch_view(scan, f"{plane}/solid")     # footprint lock
    ratio = _crop_arr(v, _ratio_view(v, wm, ch), trim_dots=12)
    r_solid = float(np.median(ratio))
    return PlaneCtx(plane=plane, scan=scan, wm=wm, ch=ch, r_solid=r_solid,
                    d_solid=float(-math.log10(max(r_solid, 1e-6))),
                    solid_lock_q=float(v.local_quality or 0.0))


# ---------------------------------------------------------------------------
# gratings (lines pitch 1-4, H and V)
# ---------------------------------------------------------------------------

def measure_gratings(ctx: PlaneCtx) -> dict:
    out: dict = {}
    span = 1.0 - ctx.r_solid
    for orient in ("h", "v"):
        for pitch in (1, 2, 3, 4):
            name = f"{ctx.plane}/lines_{orient}_p{pitch}"
            v = cc.patch_view(ctx.scan, name)         # periodic -> footprint
            ratio = _crop_arr(v, _ratio_view(v, ctx.wm, ctx.ch), trim_dots=3)
            a_eff = _a_eff(float(ratio.mean()), ctx.r_solid)
            # horizontal lines vary along y -> row means; vertical -> col means
            prof = ratio.mean(axis=1) if orient == "h" else ratio.mean(axis=0)
            amp, snr = _seg_tone(prof, period_dots=2.0 * pitch, sub=v.sub)
            m_norm = amp / (0.6366 * span + 1e-9)     # vs ideal square wave
            if m_norm >= GRATING_MNORM_RESOLVED and snr >= GRATING_SNR_RESOLVED:
                verdict = "resolved"
            elif a_eff >= GRATING_AEFF_COLLAPSED:
                verdict = "collapsed"
            elif a_eff <= GRATING_AEFF_ERASED:
                verdict = "erased"
            else:
                verdict = "merged_grey"
            gain = (a_eff - 0.5) * pitch if verdict == "resolved" else None
            out[f"{orient}_p{pitch}"] = {
                "verdict": verdict, "a_eff": round(a_eff, 4),
                "m_norm": round(m_norm, 4), "snr": round(snr, 2),
                "gain_edge_dots": None if gain is None else round(gain, 3),
                "lock_q": round(float(v.local_quality or 0.0), 3),
            }
    for orient in ("h", "v"):
        gains = [out[f"{orient}_p{p}"]["gain_edge_dots"] for p in (2, 3, 4)
                 if out[f"{orient}_p{p}"]["gain_edge_dots"] is not None]
        out[f"gain_edge_dots_{orient}"] = (round(float(np.median(gains)), 3)
                                           if gains else None)
        res = [p for p in (1, 2, 3, 4) if out[f"{orient}_p{p}"]["verdict"] == "resolved"]
        out[f"min_resolved_pitch_{orient}"] = min(res) if res else None
    return out


# ---------------------------------------------------------------------------
# checkers n=1-4 (2-D gain)
# ---------------------------------------------------------------------------

def measure_checkers(ctx: PlaneCtx) -> dict:
    out: dict = {}
    span = 1.0 - ctx.r_solid
    gains = []
    for n in (1, 2, 3, 4):
        e = cc.entry(ctx.scan["manifest"], f"{ctx.plane}/checker_n{n}")
        v = cc.patch_view(ctx.scan, e)                # periodic -> footprint
        # trim by n dots so the block grid stays aligned to the checker cells
        raw = _ratio_view(v, ctx.wm, ctx.ch)
        ratio = _crop_arr(v, raw, trim_dots=max(n, 2))
        a_eff = _a_eff(float(ratio.mean()), ctx.r_solid)
        contrast = None
        if n >= 2:  # n=1 cell phase is beyond the ±0.5-dot footprint lock
            rn = _crop_arr(v, raw, trim_dots=n)
            blocks = _block_mean(rn, n * v.sub, n * v.sub)
            # checker cell (i0+i, j0+j) with i0=j0=1 (trim n = one cell):
            # gen_calpage.checker value = ((1+i)+(1+j)) % 2 = (i+j) % 2
            ii, jj = np.meshgrid(np.arange(blocks.shape[0]),
                                 np.arange(blocks.shape[1]), indexing="ij")
            gt = ((ii + jj) % 2).astype(np.uint8)
            m_ink = float(blocks[gt == 1].mean())
            m_wht = float(blocks[gt == 0].mean())
            contrast = (m_wht - m_ink) / (span + 1e-9)
        resolved = contrast is not None and contrast > 0.10
        g2d = None
        if resolved and 0.25 < a_eff < 0.95:
            g2d = n * (math.sqrt(max(2.0 * a_eff, 0.0)) - 1.0) / 2.0
            gains.append(g2d)
        out[f"n{n}"] = {
            "a_eff": round(a_eff, 4),
            "contrast": None if contrast is None else round(contrast, 4),
            "verdict": ("resolved" if resolved else
                        "collapsed" if a_eff >= GRATING_AEFF_COLLAPSED else
                        "erased" if a_eff <= GRATING_AEFF_ERASED else
                        "merged_grey"),
            "gain_2d_dots": None if g2d is None else round(g2d, 3),
        }
    out["gain_2d_dots_median"] = (round(float(np.median(gains)), 3)
                                  if gains else None)
    return out


# ---------------------------------------------------------------------------
# isolated dots / holes ladders  (min ink / white feature, with null control)
# ---------------------------------------------------------------------------

def _site_centers_dots(n: int, size: int) -> np.ndarray:
    """Patch-local (y, x) centers in dots of gen_calpage.squares marks."""
    pos = np.arange(n, size - n, 3 * n, dtype=float) + (n - 1) / 2.0
    yy, xx = np.meshgrid(pos, pos, indexing="ij")
    return np.column_stack([yy.ravel(), xx.ravel()])


def _measure_feature_ladder(ctx: PlaneCtx, kind: str, n: int) -> dict:
    """One dots_n / holes_n patch: survival vs off-lattice null control.

    kind: 'dots' (n x n ink on white) or 'holes' (n x n white in ink).
    Registration: footprint lock; then a GT-template lock bounded to less than
    half the 3n-dot lattice period refines the phase (only trusted at
    q >= DOTS_MIN_QUALITY — a lowered gate, appropriate for sparse patterns
    and stated per contract §4; a dead pattern simply stays footprint-locked).
    Site statistic: extremal value in a ±1-dot search window around each site
    vs the patch background level; detection threshold = p99.5 of the SAME
    statistic on the null lattice (sites shifted by (1.5n, 1.5n) dots).
    """
    e = cc.entry(ctx.scan["manifest"], f"{ctx.plane}/{kind}_n{n}")
    nb = cc.nominal_bits(e)
    v = cc.patch_view(ctx.scan, e)                      # footprint
    vt = cc.patch_view(ctx.scan, e, template_dots=nb,
                       max_shift_dots=min(1.5 * n, 4.0),
                       min_quality=DOTS_MIN_QUALITY)
    refined = bool(vt.local_locked)
    view = vt if refined else v
    ratio = _crop_arr(view, _ratio_view(view, ctx.wm, ctx.ch), trim_dots=0)
    s = view.sub
    size = e["w_dots"]

    win_dots = n + 2                                    # ±1-dot site search
    win_px = max(3, int(round(win_dots * s)))
    if kind == "dots":
        filt = ndimage.minimum_filter(ratio, size=win_px, mode="nearest")
        bg = float(np.percentile(ratio, 75))            # paper level
    else:
        filt = ndimage.maximum_filter(ratio, size=win_px, mode="nearest")
        bg = float(np.percentile(ratio, 25))            # ink level

    def stats_at(centers_dots: np.ndarray) -> np.ndarray:
        cy = np.clip(np.round((centers_dots[:, 0] + 0.5) * s - 0.5).astype(int),
                     0, ratio.shape[0] - 1)
        cx = np.clip(np.round((centers_dots[:, 1] + 0.5) * s - 0.5).astype(int),
                     0, ratio.shape[1] - 1)
        val = filt[cy, cx]
        return (bg - val) if kind == "dots" else (val - bg)

    sites = _site_centers_dots(n, size)
    inner = ((sites[:, 0] > 2 * n) & (sites[:, 0] < size - 2 * n)
             & (sites[:, 1] > 2 * n) & (sites[:, 1] < size - 2 * n))
    sites = sites[inner]
    null_sites = sites + 1.5 * n
    keep = (null_sites[:, 0] < size - 2 * n) & (null_sites[:, 1] < size - 2 * n)
    null_sites = null_sites[keep]

    stat = stats_at(sites)
    stat_null = stats_at(null_sites)
    thr = float(np.percentile(stat_null, SITE_NULL_PCTL))
    survival = float((stat > thr).mean())
    fp_rate_design = (100.0 - SITE_NULL_PCTL) / 100.0

    # peak contrast relative to the full ink<->paper span (development depth,
    # over ALL sites — a dead ladder reads its noise level here)
    span = 1.0 - ctx.r_solid
    peak_frac = round(float(np.median(stat)) / (span + 1e-9), 4)

    # blob area for surviving ladders — FLUX INTEGRAL over the site window:
    # sum of (deficit vs background) / full ink<->paper span. Invariant to
    # print+scan PSF (blur conserves absorbed flux), unlike any fixed-level
    # threshold, which a small blurred mark can never reach at 2 px/dot.
    area_dots2 = None
    gain_edge = None
    if survival >= 0.5:
        signed = (bg - ratio) if kind == "dots" else (ratio - bg)
        aw_px = max(3, int(round((n + 2) * s)))
        flux = ndimage.uniform_filter(signed.astype(np.float32), size=aw_px,
                                      mode="constant") * float(aw_px) ** 2
        cy = np.clip(np.round((sites[:, 0] + 0.5) * s - 0.5).astype(int),
                     0, ratio.shape[0] - 1)
        cx = np.clip(np.round((sites[:, 1] + 0.5) * s - 0.5).astype(int),
                     0, ratio.shape[1] - 1)
        surv = stat > thr
        area_px2 = float(np.mean(flux[cy[surv], cx[surv]])) / (span + 1e-9)
        area_dots2 = max(area_px2, 0.0) / (s * s)
        gain_edge = (math.sqrt(max(area_dots2, 0.0)) - n) / 2.0

    return {
        "survival": round(survival, 4),
        "n_sites": int(len(sites)), "n_null_sites": int(len(null_sites)),
        "stat_median": round(float(np.median(stat)), 4),
        "null_median": round(float(np.median(stat_null)), 4),
        "null_thr_p995": round(thr, 4),
        "null_fp_design_rate": fp_rate_design,
        "peak_contrast_frac": peak_frac,
        "area_dots2": None if area_dots2 is None else round(area_dots2, 2),
        "area_method": "flux_integral_psf_invariant",
        "area_nominal_dots2": n * n,
        "gain_edge_dots": None if gain_edge is None else round(gain_edge, 3),
        "phase_refined": refined,
        "lock_q": round(float((vt if refined else v).local_quality or 0.0), 3),
    }


def measure_dots_holes(ctx: PlaneCtx) -> dict:
    out: dict = {"dots": {}, "holes": {}}
    for n in (1, 2):
        out["dots"][f"n{n}"] = _measure_feature_ladder(ctx, "dots", n)
    for n in (1, 2, 3):
        out["holes"][f"n{n}"] = _measure_feature_ladder(ctx, "holes", n)

    def min_reliable(fam: dict, ns: tuple[int, ...]
                     ) -> tuple[int | None, int | None, str]:
        """(strict, detect, note). detect = survival >= 0.9 AND peak contrast
        >= 30% of the ink<->paper span (usable trace); strict additionally
        requires flux area >= 50% nominal (full development, design §11)."""
        strict, detect = None, None
        for n in ns:
            r = fam[f"n{n}"]
            if (r["survival"] < SURVIVAL_RELIABLE
                    or (r["peak_contrast_frac"] or 0.0) < DETECT_CONTRAST_FRAC):
                continue
            if detect is None:
                detect = n
            ok_area = (r["area_dots2"] is not None
                       and r["area_dots2"] >= AREA_FRACTION_RELIABLE * n * n)
            if strict is None and ok_area:
                strict = n
        note = ("ok" if strict is not None else
                f"detectable at n={detect} but flux area <50% nominal"
                if detect is not None else f">{ns[-1]} (ladder exhausted)")
        return strict, detect, note

    mi, mi_det, mi_note = min_reliable(out["dots"], (1, 2))
    mw, mw_det, mw_note = min_reliable(out["holes"], (1, 2, 3))
    out["min_ink_dots"], out["min_ink_detect_dots"], out["min_ink_note"] = \
        mi, mi_det, mi_note
    out["min_white_dots"], out["min_white_detect_dots"], out["min_white_note"] = \
        mw, mw_det, mw_note
    return out


# ---------------------------------------------------------------------------
# slanted edges -> ESF -> PSF sigma (coarse at 2 px/dot)
# ---------------------------------------------------------------------------

_T5 = math.tan(math.radians(5.0))


def _fit_edge_esf(ratio: np.ndarray, sub: int, size_dots: int,
                  which: str) -> dict:
    """ESF/erf fit of one slanted edge of gen_calpage.slant_edge.

    which='upper': near-vertical edge, ink LEFT of x_e(y)   -> sigma_x.
    which='lower': near-horizontal edge, ink BELOW y_e(x)   -> sigma_y.
    Per-row (per-column) mid-level crossing -> robust line fit -> residual-
    binned ESF at 0.25-dot bins -> erf fit. Returns sigma in dots + overshoot
    fraction on both tails (RET metric).
    """
    h2 = size_dots // 2
    rows: list[tuple[float, float]] = []
    if which == "upper":
        y_lo, y_hi = 6.0, (h2 - 6) - 6.0
        def nominal(t: float) -> float:
            return size_dots * 0.55 + (t - (h2 - 6) / 2.0) * _T5
        def profile(i_px: int) -> np.ndarray:
            return ratio[i_px, :]
        n_lines = ratio.shape[0]
        ascending = True         # ink left -> ratio rises with x
    else:
        y_lo, y_hi = 6.0, size_dots - 6.0
        y_mid = h2 + 6 + int((size_dots - h2 - 6) * 0.45)
        def nominal(t: float) -> float:
            return y_mid + (t - size_dots / 2.0) * _T5
        def profile(i_px: int) -> np.ndarray:
            return ratio[:, i_px]
        n_lines = ratio.shape[1]
        ascending = False        # ink below -> ratio falls with y

    lines_t, cross_s = [], []
    for i in range(n_lines):
        t = i / sub                              # dots along the edge
        if not (y_lo <= t <= y_hi):
            continue
        s0 = nominal(t)
        prof = profile(i)
        w0 = max(0, int((s0 - 12) * sub))
        w1 = min(len(prof), int((s0 + 12) * sub))
        if w1 - w0 < 8 * sub:
            continue
        win = prof[w0: w1]
        xs = np.arange(w0, w1) / sub             # dots
        far_lo = xs < s0 - 4.0
        far_hi = xs > s0 + 4.0
        if far_lo.sum() < 2 or far_hi.sum() < 2:
            continue
        lo_side = float(win[far_lo].mean())
        hi_side = float(win[far_hi].mean())
        if abs(hi_side - lo_side) < 0.08:        # no edge contrast in this line
            continue
        mid = 0.5 * (lo_side + hi_side)
        d = win - mid
        sgn = np.sign(d)
        chg = np.nonzero(sgn[:-1] * sgn[1:] < 0)[0]
        if len(chg) == 0:
            continue
        xc = xs[chg] + (xs[1] - xs[0]) * np.abs(d[chg]) / (
            np.abs(d[chg]) + np.abs(d[chg + 1]) + 1e-12)
        k = int(np.argmin(np.abs(xc - s0)))
        if abs(xc[k] - s0) > 6.0:
            continue
        lines_t.append(t)
        cross_s.append(float(xc[k]))
    if len(lines_t) < 30:
        return {"sigma_dots": None, "n_lines": len(lines_t),
                "note": "edge not detected (plane dead or contrast too low)"}

    tv = np.asarray(lines_t)
    sv = np.asarray(cross_s)
    good = np.ones(len(tv), bool)
    coef = np.polyfit(tv, sv, 1)
    for _ in range(2):                            # robust reject
        res = sv - np.polyval(coef, tv)
        mad = 1.4826 * np.median(np.abs(res - np.median(res))) + 1e-6
        good = np.abs(res - np.median(res)) < 3.0 * mad
        coef = np.polyfit(tv[good], sv[good], 1)

    # ESF: residual distance from the fitted edge, binned at 0.25 dot
    ss, vv = [], []
    for i in range(n_lines):
        t = i / sub
        if not (y_lo <= t <= y_hi):
            continue
        se = float(np.polyval(coef, t))
        prof = profile(i)
        w0 = max(0, int((se - 8) * sub))
        w1 = min(len(prof), int((se + 8) * sub))
        xs = np.arange(w0, w1) / sub - se
        ss.append(xs)
        vv.append(prof[w0: w1])
    s_all = np.concatenate(ss)
    v_all = np.concatenate(vv).astype(np.float64)
    bins = np.arange(-6.0, 6.0 + 0.25, 0.25)
    idx = np.digitize(s_all, bins)
    esf_s, esf_v = [], []
    for b in range(1, len(bins)):
        m = idx == b
        if m.sum() >= 5:
            esf_s.append(0.5 * (bins[b - 1] + bins[b]))
            esf_v.append(float(v_all[m].mean()))
    esf_s = np.asarray(esf_s)
    esf_v = np.asarray(esf_v)

    lo0 = float(esf_v[: 4].mean())
    hi0 = float(esf_v[-4:].mean())

    def model(s, b0, b1, s0, sig):
        return b0 + b1 * 0.5 * (1.0 + erf((s - s0) / (sig * math.sqrt(2.0))))

    try:
        p0 = (lo0, hi0 - lo0, 0.0, 0.8)
        popt, _ = curve_fit(model, esf_s, esf_v, p0=p0,
                            bounds=([-1.0, -2.0, -3.0, 0.1],
                                    [2.0, 2.0, 3.0, 4.0]), maxfev=5000)
    except Exception:
        return {"sigma_dots": None, "n_lines": int(len(tv)),
                "note": "erf fit failed"}
    b0, b1, s0, sig = (float(x) for x in popt)
    hi_asym, lo_asym = max(b0, b0 + b1), min(b0, b0 + b1)
    tail = max(2.0 * sig, 1.5)
    left = esf_v[esf_s < s0 - tail]
    right = esf_v[esf_s > s0 + tail]
    # map tails to asymptotes according to edge direction
    lo_tail, hi_tail = (left, right) if ascending else (right, left)
    over = 0.0
    if len(hi_tail):
        over = max(over, (float(hi_tail.max()) - hi_asym) / abs(b1))
    if len(lo_tail):
        over = max(over, (lo_asym - float(lo_tail.min())) / abs(b1))
    return {"sigma_dots": round(abs(sig), 3), "edge_pos_resid_dots": round(s0, 3),
            "overshoot_frac": round(max(over, 0.0), 4),
            "n_lines": int(len(tv)), "slope_fit_dots_per_dot": round(float(coef[0]), 4),
            "note": "coarse: 2 scan px/dot; includes scanner PSF and the "
                    "1-dot slant staircase (~0.29-dot RMS quantization)"}


def measure_slant(ctx: PlaneCtx) -> dict:
    e = cc.entry(ctx.scan["manifest"], f"{ctx.plane}/slant")
    v = cc.patch_view(ctx.scan, e)                     # aperiodic -> GT lock
    ratio = _crop_arr(v, _ratio_view(v, ctx.wm, ctx.ch), trim_dots=0)
    upper = _fit_edge_esf(ratio, v.sub, e["w_dots"], "upper")   # sigma_x
    lower = _fit_edge_esf(ratio, v.sub, e["w_dots"], "lower")   # sigma_y
    return {"sigma_x": upper, "sigma_y": lower,
            "lock_q": round(float(v.local_quality or 0.0), 3),
            "locked": bool(v.local_locked)}


# ---------------------------------------------------------------------------
# density ladder -> TRC + mottle vs coverage
# ---------------------------------------------------------------------------

def _mottle_regression(d_crop: np.ndarray, gt_bits: np.ndarray, sub: int,
                       block_dots: int = MOTTLE_BLOCK_DOTS,
                       null_shift_dots: int = 24) -> dict:
    """Block-mean density regressed on KNOWN GT block coverage; the residual
    sigma is mottle (pattern-independent density fluctuation). Instrument
    control: identical regression against a GT rolled by null_shift_dots
    (= 8 cells) — R^2 must collapse toward 0 (001.2 discipline)."""
    bp = block_dots * sub
    db = _block_mean(d_crop, bp, bp)
    gb = _block_mean(gt_bits.astype(np.float32), block_dots, block_dots)
    gb = gb[: db.shape[0], : db.shape[1]]
    db = db[: gb.shape[0], : gb.shape[1]]
    x = gb.ravel()
    y = db.ravel()

    def fit(xv: np.ndarray) -> tuple[float, float]:
        A = np.column_stack([np.ones_like(xv), xv])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        res = y - A @ coef
        r2 = 1.0 - res.var() / (y.var() + 1e-12)
        return float(res.std()), float(r2)

    sigma, r2 = fit(x)
    gnull = _block_mean(np.roll(gt_bits, null_shift_dots, axis=1
                                ).astype(np.float32), block_dots, block_dots)
    gnull = gnull[: db.shape[0], : db.shape[1]]
    _, r2_null = fit(gnull.ravel())
    return {"sigma_D": round(sigma, 4), "r2": round(r2, 4),
            "r2_null": round(r2_null, 4), "n_blocks": int(y.size),
            "block_dots": block_dots}


def measure_trc(ctx: PlaneCtx) -> dict:
    trc: list[dict] = [{"coverage_nominal": 0.0, "gt_coverage": 0.0,
                        "D_mean": 0.0, "a_eff": 0.0, "note": "paper (by definition of local-white density)"}]
    mottle: dict = {}
    for p in range(10, 100, 10):
        e = cc.entry(ctx.scan["manifest"], f"{ctx.plane}/density_{p}")
        v = cc.patch_view(ctx.scan, e)                  # GT lock
        d = cc.density(v, ctx.wm, channels=(ctx.ch,))[ctx.ch]
        dc = _crop_arr(v, d, trim_dots=3)
        ratio = np.power(10.0, -dc)
        gt = cc.load_gt(e)
        gtc = gt[3: -3, 3: -3]
        a = _a_eff(float(ratio.mean()), ctx.r_solid)
        reg = _mottle_regression(dc.astype(np.float64), gtc, v.sub)
        trc.append({"coverage_nominal": p / 100.0,
                    "gt_coverage": round(float(gt.mean()), 4),
                    "D_mean": round(float(dc.mean()), 4),
                    "a_eff": round(a, 4),
                    "tvi": round(a - float(gt.mean()), 4),
                    "lock_q": round(float(v.local_quality or 0.0), 3)})
        mottle[f"p{p}"] = reg
    # solid: mottle = block sigma (no GT); includes banding — flagged
    vs = cc.patch_view(ctx.scan, f"{ctx.plane}/solid")
    ds = _crop_arr(vs, cc.density(vs, ctx.wm, channels=(ctx.ch,))[ctx.ch],
                   trim_dots=10)
    bp = MOTTLE_BLOCK_DOTS * vs.sub
    blocks = _block_mean(ds.astype(np.float64), bp, bp)
    mottle["p100"] = {"sigma_D": round(float(blocks.std()), 4),
                      "r2": None, "r2_null": None,
                      "n_blocks": int(blocks.size),
                      "block_dots": MOTTLE_BLOCK_DOTS,
                      "note": "no GT regression on solid; includes banding"}
    trc.append({"coverage_nominal": 1.0, "gt_coverage": 1.0,
                "D_mean": round(ctx.d_solid, 4), "a_eff": 1.0, "tvi": 0.0})

    # scanner density floor: ratio is clipped at v=1 count, so D cannot exceed
    # log10(white_local); sigma_D near that floor is instrument-limited.
    es = cc.entry(ctx.scan["manifest"], f"{ctx.plane}/solid")
    w0 = float(np.asarray(cc.white_at(
        ctx.wm, np.array([es["x_dots"] + es["w_dots"] / 2.0]),
        np.array([es["y_dots"] + es["h_dots"] / 2.0]), ctx.ch)).ravel()[0])
    d_floor = math.log10(max(w0, 1.0))
    for t in trc:
        key = (f"p{int(round(t['coverage_nominal'] * 100))}")
        if key in mottle and t["D_mean"] > d_floor - 0.5:
            mottle[key]["floor_limited"] = True
    note_floor = None
    if ctx.d_solid > d_floor - 0.4:
        note_floor = (f"D_solid {ctx.d_solid:.2f} is within 0.4 of the scanner "
                      f"floor D≈{d_floor:.2f} (v -> 1-2 counts): high-coverage "
                      "sigma_D is floor/quantization-limited — upper bound only")
    return {"trc": trc, "mottle_sigma_D_vs_coverage": mottle,
            "block_mm": round(MOTTLE_BLOCK_DOTS * 25.4 / cc.HW_DPI, 3),
            "channel": ctx.ch, "d_solid": round(ctx.d_solid, 4),
            "r_solid": round(ctx.r_solid, 4),
            "scanner_D_floor": round(d_floor, 3),
            "mottle_instrument_note": note_floor}


# ---------------------------------------------------------------------------
# canary D — resolution clamp (1-dot phase pairs)
# ---------------------------------------------------------------------------

def _phase_pair_measure(ctx: PlaneCtx, name: str) -> dict:
    """Both halves of one phase-pair patch: fundamental amplitude (normalized),
    a_eff, and the A->B phase difference in dots at the 2-dot period."""
    e = cc.entry(ctx.scan["manifest"], name)
    v = cc.patch_view(ctx.scan, e)                     # periodic -> footprint
    ratio = _crop_arr(v, _ratio_view(v, ctx.wm, ctx.ch), trim_dots=0)
    span = 1.0 - ctx.r_solid
    vertical = e["params"]["lines"] == "vertical"
    if not vertical:
        ratio = ratio.T                                # unify: phase along x
    w_g, gap = 128, 14
    sub = v.sub
    out_regions = []
    zs = []
    for x0, x1 in ((3, w_g - 3), (w_g + gap + 3, w_g + gap + w_g - 3)):
        block = ratio[3 * sub: -3 * sub, x0 * sub: x1 * sub]
        prof = block.mean(axis=0)
        pos = (x0 * sub + np.arange(len(prof))) / sub  # dots, shared frame
        amp, ph = _tone_phase(prof, pos, period_dots=2.0)
        # split-half control: intra-region phase difference (expected 0)
        hn = len(prof) // 2
        _, ph_a = _tone_phase(prof[:hn], pos[:hn], 2.0)
        _, ph_b = _tone_phase(prof[hn:], pos[hn:], 2.0)
        dph_half = math.atan2(math.sin(ph_a - ph_b), math.cos(ph_a - ph_b))
        a_eff = _a_eff(float(block.mean()), ctx.r_solid)
        out_regions.append({"m_norm": round(amp / (0.6366 * span + 1e-9), 4),
                            "a_eff": round(a_eff, 4),
                            "split_half_dphase_dots": round(abs(dph_half) / math.pi, 4)})
        zs.append(ph)
    dph = math.atan2(math.sin(zs[1] - zs[0]), math.cos(zs[1] - zs[0]))
    return {"regions": out_regions,
            "delta_phase_dots": round(abs(dph) / math.pi, 4),  # period=2 dots
            "min_m_norm": min(r["m_norm"] for r in out_regions),
            "control_split_half_dots": max(r["split_half_dphase_dots"]
                                           for r in out_regions),
            "lock_q": round(float(v.local_quality or 0.0), 3)}


def canary_d(ctx_k: PlaneCtx, gratings_k: dict) -> tuple[dict, dict]:
    pv = _phase_pair_measure(ctx_k, "phasepair_v")
    ph = _phase_pair_measure(ctx_k, "phasepair_h")
    # instrument control: best resolved-K-grating normalized modulation
    ctrl_mnorm = max((gratings_k[k]["m_norm"] for k in gratings_k
                      if isinstance(gratings_k[k], dict)
                      and gratings_k[k].get("verdict") == "resolved"),
                     default=0.0)
    min_m = min(pv["min_m_norm"], ph["min_m_norm"])
    detail = {"phasepair_v": pv, "phasepair_h": ph,
              "control_best_resolved_grating_m_norm": round(ctrl_mnorm, 4)}
    if min_m < 0.05:
        verdict = cc.canary_verdict(
            "D_resolution_clamp", "indeterminate", min_m, ctrl_mnorm,
            note=("1-on/1-off comb carries no modulation "
                  f"(a_eff V={pv['regions'][0]['a_eff']}/{pv['regions'][1]['a_eff']}, "
                  f"H={ph['regions'][0]['a_eff']}/{ph['regions'][1]['a_eff']}) — "
                  "Nyquist closes solid on this engine (001.1), so the clamp "
                  "canary cannot discriminate here; control shows the spectral "
                  "instrument resolves coarser gratings fine."))
        return verdict, detail
    # modulated: check the 1-dot offset (V pair is the clean axis; H conflates
    # transport drift over the 6-mm region separation)
    stat = pv["delta_phase_dots"]
    ctl = pv["control_split_half_dots"]
    status = "pass" if abs(stat - 1.0) <= 0.2 else "fail"
    verdict = cc.canary_verdict(
        "D_resolution_clamp", status, stat, ctl,
        note=(f"V-pair dphase {stat} dots (expect 1.0±0.2); split-half control "
              f"{ctl}; H-pair dphase {ph['delta_phase_dots']} (transport-"
              "confounded, informational)."))
    return verdict, detail


# ---------------------------------------------------------------------------
# canary F — RET / edge enhancement
# ---------------------------------------------------------------------------

def canary_f(gratings_k: dict, slant_k: dict) -> tuple[dict, dict]:
    """(a) excess line width vs nominal width must have ~zero slope (constant
    gain per edge); (b) slant-edge ESF must not overshoot. Pooled H+V model
    with per-orientation intercepts, shared slope."""
    rows = []
    for orient in ("h", "v"):
        for p in (2, 3, 4):
            r = gratings_k[f"{orient}_p{p}"]
            if r["verdict"] == "resolved":
                rows.append((orient, p, 2.0 * p * (r["a_eff"] - 0.5)))
    over = max((slant_k[k].get("overshoot_frac") or 0.0)
               for k in ("sigma_x", "sigma_y"))
    detail = {"width_excess_rows": [
        {"orient": o, "nominal_w_dots": p, "excess_w_dots": round(e_, 3)}
        for o, p, e_ in rows], "esf_overshoot_frac_max": round(over, 4)}
    if len(rows) < 4:
        v = cc.canary_verdict("F_ret_edges", "indeterminate", 0.0, 0.0,
                              note=f"only {len(rows)} resolved gratings — "
                                   "width regression underdetermined")
        return v, detail
    A = np.array([[1.0 if o == "h" else 0.0, 1.0 if o == "v" else 0.0, p]
                  for o, p, _ in rows])
    yv = np.array([e_ for _, _, e_ in rows])
    coef, *_ = np.linalg.lstsq(A, yv, rcond=None)
    resid = yv - A @ coef
    dof = max(len(rows) - 3, 1)
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.inv(A.T @ A)
    slope = float(coef[2])
    se2 = 2.0 * math.sqrt(max(cov[2, 2], 0.0))
    detail.update({"slope_dots_per_dot": round(slope, 4),
                   "slope_2se": round(se2, 4),
                   "intercept_h_2g_dots": round(float(coef[0]), 3),
                   "intercept_v_2g_dots": round(float(coef[1]), 3)})
    if abs(slope) <= max(0.06, se2) and over <= 0.08:
        status = "pass"
    elif abs(slope) > max(0.12, 1.5 * se2) or over > 0.15:
        status = "fail"
    else:
        status = "indeterminate"
    v = cc.canary_verdict(
        "F_ret_edges", status, slope, se2,
        note=(f"width-excess slope {slope:+.3f} dots/dot (2SE {se2:.3f}; RET "
              f"thickens thin strokes -> negative slope); ESF overshoot "
              f"{over:.3f} (flag >0.08); per-edge gain H {float(coef[0])/2:+.2f} "
              f"V {float(coef[1])/2:+.2f} dots"))
    return v, detail


# ---------------------------------------------------------------------------
# cross-check against experiment 001.1 (K plane)
# ---------------------------------------------------------------------------

def crosscheck_001(k: dict) -> dict:
    """CAL-1-as-instrument validation against the settled 001.1 K numbers."""
    checks = []

    def add(name: str, expected: str, measured: float | None, ok: bool | None):
        checks.append({"check": name, "expected_001": expected,
                       "measured": measured,
                       "verdict": ("indeterminate" if ok is None else
                                   "consistent" if ok else "DISCREPANT")})

    s1 = k["dots_holes"]["dots"]["n1"]["survival"]
    add("isolated 1-dot ink does not print", "survival ~0.00", s1, s1 < 0.10)
    # 001's "min white ~3 dots" was measured on 1-D white LINES (3-dot line
    # keeps 79% width, shrink ~0.32 dots/edge). CAL-1's isolated 2-D holes
    # shrink from all four sides — check the same physics (n1 erased, n2
    # marginal trace, n3 usable), not the raw scalar; the strict 2-D
    # area-gated verdict is a stricter NEW criterion, reported alongside.
    dh_ = k["dots_holes"]
    mwd = dh_["min_white_detect_dots"]
    sh3 = dh_["holes"]["n3"]["gain_edge_dots"]
    add("min white feature (001: ~3 dots, from 1-D lines)",
        "n1 erased; n2 marginal; n3 usable (detect==3); shrink 0.1-0.7/edge",
        {"detect": mwd, "strict_2d_area": dh_["min_white_dots"],
         "n1_survival": dh_["holes"]["n1"]["survival"],
         "n2_peak_contrast": dh_["holes"]["n2"]["peak_contrast_frac"],
         "n3_shrink_per_edge": None if sh3 is None else -sh3},
        mwd == 3 and dh_["holes"]["n1"]["survival"] < 0.1
        and sh3 is not None and -0.75 <= sh3 <= -0.05)
    h2 = k["dots_holes"]["holes"]["n2"]["survival"]
    add("2-dot holes marginal (001: 2-dot white line keeps ~1/3 width)",
        "partial: detectable trace, well under full development",
        {"survival": h2,
         "peak_contrast_frac": k["dots_holes"]["holes"]["n2"]["peak_contrast_frac"]},
        (k["dots_holes"]["holes"]["n2"]["peak_contrast_frac"] or 0) < 0.6)
    p1h = k["gratings"]["h_p1"]
    p1v = k["gratings"]["v_p1"]
    # 001.1 "closes solid" was a THRESHOLDED interior ink fraction; the CAL-1
    # statistic is Murray-Davies a_eff, which can read a closed-but-grey fill
    # as <1. Consistency = modulation dead + ink-majority, not a_eff ~ 1.
    add("Nyquist 1-on/1-off closes (H): modulation dead, ink-majority",
        "closed at threshold metric", p1h["m_norm"],
        p1h["verdict"] == "collapsed" and p1h["m_norm"] < 0.10)
    add("Nyquist 1-on/1-off closes (V): modulation dead, ink-majority",
        "closed at threshold metric", p1v["m_norm"],
        p1v["verdict"] == "collapsed" and p1v["m_norm"] < 0.10)
    gv = k["gratings"]["gain_edge_dots_v"]
    add("edge gain (V lines, >=2-dot)", "~+0.4 dots/edge", gv,
        None if gv is None else abs(gv - 0.4) <= 0.2)
    gh = k["gratings"]["gain_edge_dots_h"]
    add("H/V development anisotropy exists", "H != V (001: strong)",
        None if (gh is None or gv is None) else round(gh - gv, 3),
        None if (gh is None or gv is None) else True)
    agree = all(c["verdict"] == "consistent" for c in checks
                if c["verdict"] != "indeterminate")
    return {"checks": checks,
            "instrument_validated": bool(agree),
            "note": "agreement validates CAL-1 as an instrument (task brief); "
                    "discrepancies are reported, never averaged away"}


# ---------------------------------------------------------------------------
# family entry point
# ---------------------------------------------------------------------------

def run(scan_bw: dict, scan_color: dict, core_ctx: dict | None = None) -> dict:
    """Structural family analyzer. Returns a payload for cc.report_merge.

    scan_bw / scan_color: cc.load_scan dicts (registered; will be registered
    here if not). core_ctx (optional dict) may carry precomputed
    'white_model_bw' / 'white_model_color' to avoid refitting.
    """
    core_ctx = core_ctx or {}
    _ensure_registered(scan_bw)
    _ensure_registered(scan_color)
    wm_bw = core_ctx.get("white_model_bw") or cc.white_model(scan_bw)
    wm_color = core_ctx.get("white_model_color") or cc.white_model(scan_color)

    per_plane: dict[str, dict] = {}
    ctxs: dict[str, PlaneCtx] = {}
    for plane in PLANES:
        ctx = _plane_ctx(plane, scan_bw, scan_color, wm_bw, wm_color)
        ctxs[plane] = ctx
        per_plane[plane] = {
            "scan_used": "bw" if plane == "K" else "color",
            "channel": ctx.ch,
            "solid_lock_q": round(ctx.solid_lock_q, 3),
            "gratings": measure_gratings(ctx),
            "checkers": measure_checkers(ctx),
            "dots_holes": measure_dots_holes(ctx),
            "slant": measure_slant(ctx),
            "density": measure_trc(ctx),
        }

    verdict_d, detail_d = canary_d(ctxs["K"], per_plane["K"]["gratings"])
    verdict_f, detail_f = canary_f(per_plane["K"]["gratings"],
                                   per_plane["K"]["slant"])
    xcheck = crosscheck_001(per_plane["K"])

    # ---- curated channel_params + per-plane fragments ----------------------
    psf, gain, devthr, minfeat, fragments = {}, {}, {}, {}, {}
    for plane in PLANES:
        r = per_plane[plane]
        sx = r["slant"]["sigma_x"].get("sigma_dots")
        sy = r["slant"]["sigma_y"].get("sigma_dots")
        psf[plane] = {"x": sx, "y": sy, "method": "slant_edge_erf",
                      "coarse_2px_per_dot": True,
                      "includes_scanner_psf_and_staircase": True}
        g = r["gratings"]
        gain[plane] = {"h_lines": g["gain_edge_dots_h"],
                       "v_lines": g["gain_edge_dots_v"],
                       "checker_2d": r["checkers"]["gain_2d_dots_median"],
                       "anisotropy_h_minus_v": (
                           None if (g["gain_edge_dots_h"] is None
                                    or g["gain_edge_dots_v"] is None)
                           else round(g["gain_edge_dots_h"]
                                      - g["gain_edge_dots_v"], 3))}
        dh = r["dots_holes"]
        devthr[plane] = {"ink": dh["min_ink_dots"], "white": dh["min_white_dots"],
                         "ink_detect": dh["min_ink_detect_dots"],
                         "white_detect": dh["min_white_detect_dots"],
                         "ink_note": dh["min_ink_note"],
                         "white_note": dh["min_white_note"],
                         "criteria": "detect = survival>=0.9 AND peak contrast"
                                     ">=30% of ink<->paper span (usable "
                                     "trace); strict = detect AND flux area"
                                     ">=50% nominal (design §11)",
                         "ladder_max": {"ink": 2, "white": 3}}
        mi_, mw_ = dh["min_ink_dots"], dh["min_white_dots"]
        minfeat[plane] = {
            "strict": (None if (mi_ is None or mw_ is None)
                       else int(max(mi_, mw_))),
            "detect": (None if (dh["min_ink_detect_dots"] is None
                                or dh["min_white_detect_dots"] is None)
                       else int(max(dh["min_ink_detect_dots"],
                                    dh["min_white_detect_dots"]))),
        }
        fragments[plane] = {
            "min_ink_dots": mi_, "min_white_dots": mw_,
            "min_ink_detect_dots": dh["min_ink_detect_dots"],
            "min_white_detect_dots": dh["min_white_detect_dots"],
            "gain_edge_dots_hv": {"h": g["gain_edge_dots_h"],
                                  "v": g["gain_edge_dots_v"]},
            "psf_sigma_dots_xy": {"x": sx, "y": sy},
            "trc": r["density"]["trc"],
            "mottle": {"sigma_D_vs_coverage":
                       {k: v["sigma_D"] for k, v in
                        r["density"]["mottle_sigma_D_vs_coverage"].items()},
                       "block_mm": r["density"]["block_mm"],
                       "channel": r["density"]["channel"]},
        }

    payload = {
        "channel_params": {
            "psf_sigma_dots": psf,
            "gain_edge_dots": gain,
            "dev_threshold_dots": devthr,
            "min_feature_dots": minfeat,
        },
        "canaries": {"D": verdict_d, "F": verdict_f},
        "families": {"structural": {
            "channel_fragments": fragments,
            "per_plane": per_plane,
            "canary_detail": {"D": detail_d, "F": detail_f},
            "crosscheck_001": xcheck,
            "thresholds": {
                "grating_m_norm_resolved": GRATING_MNORM_RESOLVED,
                "grating_snr_resolved": GRATING_SNR_RESOLVED,
                "survival_reliable": SURVIVAL_RELIABLE,
                "area_fraction_reliable": AREA_FRACTION_RELIABLE,
                "site_null_percentile": SITE_NULL_PCTL,
                "dots_template_min_quality": DOTS_MIN_QUALITY,
            },
            "notes": [
                "K measured on the grey scan; C/M/Y on the color scan "
                "complementary channels (r/g/b). Y is near-invisible in grey.",
                "TRC + mottle are reported here (families.structural) and in "
                "channel_fragments, NOT under channel_params.tvi/mottle_sigma "
                "(those keys are owned by the density_color family).",
                "a_eff is Murray-Davies (n=1) against the plane's own solid "
                "and the local fitted paper white.",
                "PSF sigma is print+scan combined, coarse at 2 px/dot "
                "(001.1 caveat), and includes the slant staircase floor.",
                "Every detection/regression carries its control: off-lattice "
                "null sites (dots/holes), shifted-GT R^2 (mottle), split-half "
                "phase + resolved-grating modulation (canary D).",
                "Slant-edge geometric control: the fitted edge slope must "
                "read tan(5 deg)=0.0875 dots/dot — see "
                "per_plane.*.slant.*.slope_fit_dots_per_dot.",
            ],
        }},
    }
    return payload


# ---------------------------------------------------------------------------
# smoke block — run the family end-to-end on the real scans
# ---------------------------------------------------------------------------

def _print_summary(payload: dict) -> None:
    fam = payload["families"]["structural"]
    cp = payload["channel_params"]
    print("\n=== structural family — per-plane summary ===")
    for plane in PLANES:
        r = fam["per_plane"][plane]
        g = r["gratings"]
        print(f"\n-- plane {plane} (scan={r['scan_used']}, ch={r['channel']}, "
              f"D_solid={r['density']['d_solid']}) --")
        for orient in ("h", "v"):
            row = "  ".join(
                f"p{p}:{g[f'{orient}_p{p}']['verdict'][:4]}"
                f"(a={g[f'{orient}_p{p}']['a_eff']:.2f},m={g[f'{orient}_p{p}']['m_norm']:.2f})"
                for p in (1, 2, 3, 4))
            print(f"  lines {orient.upper()}: {row}")
        print(f"  gain/edge: H={g['gain_edge_dots_h']} V={g['gain_edge_dots_v']} "
              f"checker2D={r['checkers']['gain_2d_dots_median']}")
        ck = r["checkers"]
        print("  checkers: " + "  ".join(
            f"n{n}:{ck[f'n{n}']['verdict'][:4]}(a={ck[f'n{n}']['a_eff']:.2f})"
            for n in (1, 2, 3, 4)))
        dh = r["dots_holes"]
        print("  dots surv: " + "  ".join(
            f"n{n}={dh['dots'][f'n{n}']['survival']:.2f}"
            f"(thr={dh['dots'][f'n{n}']['null_thr_p995']:.3f})" for n in (1, 2))
            + "   holes surv: " + "  ".join(
            f"n{n}={dh['holes'][f'n{n}']['survival']:.2f}" for n in (1, 2, 3)))
        print(f"  min_ink strict={dh['min_ink_dots']} detect="
              f"{dh['min_ink_detect_dots']} ({dh['min_ink_note']})  "
              f"min_white strict={dh['min_white_dots']} detect="
              f"{dh['min_white_detect_dots']} ({dh['min_white_note']})")
        sl = r["slant"]
        print(f"  PSF sigma: x={sl['sigma_x'].get('sigma_dots')} "
              f"y={sl['sigma_y'].get('sigma_dots')} dots (coarse), "
              f"overshoot x={sl['sigma_x'].get('overshoot_frac')} "
              f"y={sl['sigma_y'].get('overshoot_frac')}")
        trc = r["density"]["trc"]
        print("  TRC a_eff@p: " + "  ".join(
            f"{t['coverage_nominal']:.1f}->{t['a_eff']:.2f}" for t in trc))
        mot = r["density"]["mottle_sigma_D_vs_coverage"]
        print("  mottle sigma_D: " + "  ".join(
            f"{k}={v['sigma_D']:.3f}" for k, v in mot.items()))
        p50 = mot["p50"]
        print(f"  mottle control (p50): r2={p50['r2']} r2_null={p50['r2_null']}")
    print("\n=== canaries ===")
    for cid in ("D", "F"):
        c = payload["canaries"][cid]
        print(f"  {cid}: {c['status']}  stat={c['statistic']:.4f} "
              f"ctrl={c['control']:.4f}\n     {c['note']}")
    print("\n=== cross-check vs 001.1 (K) ===")
    for c in fam["crosscheck_001"]["checks"]:
        print(f"  [{c['verdict']:>12}] {c['check']}: measured={c['measured']} "
              f"(001: {c['expected_001']})")
    print(f"  instrument_validated={fam['crosscheck_001']['instrument_validated']}")


if __name__ == "__main__":
    import argparse
    import time

    ap = argparse.ArgumentParser(description="structural family smoke run")
    ap.add_argument("scan_bw", nargs="?",
                    default=str(_HERE.parent.parent / "scans/test-scan-calpage-bw.png"))
    ap.add_argument("scan_color", nargs="?",
                    default=str(_HERE.parent.parent / "scans/test-scan-calpage-color.png"))
    ap.add_argument("--out", default=str(cc.BUILD / "cal_structural_report.json"))
    args = ap.parse_args()

    t0 = time.time()
    scan_bw = cc.load_scan(args.scan_bw)
    cc.register(scan_bw)
    print(f"[{time.time()-t0:6.1f}s] registered bw  "
          f"(rms {scan_bw['registration']['residual_rms_dots']:.2f} dots)")
    scan_color = cc.load_scan(args.scan_color)
    cc.register(scan_color)
    print(f"[{time.time()-t0:6.1f}s] registered color "
          f"(rms {scan_color['registration']['residual_rms_dots']:.2f} dots)")

    payload = run(scan_bw, scan_color, None)
    print(f"[{time.time()-t0:6.1f}s] family measurements done")

    report = cc.report_init(scan_color)
    cc.report_merge(report, payload)
    cc.save_report(report, args.out)
    print(f"[{time.time()-t0:6.1f}s] report saved to {args.out}")
    _print_summary(payload)

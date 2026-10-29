"""cal_canary — canary suite + machine-strip self-report (experiment 002).

Family "canaries + self-report" on the real CAL-1 scans. Everything goes
through cal_core (ANALYZER-CONTRACT.md): registration, patch views and the
canary_verdict shape. Per the 001.2 discipline every verdict is
{pass|fail|indeterminate} + measured statistic + discriminating control value
— never a bare boolean. The machine-strip decode (canary f / selfreport) is
validated by its own CRC-16/parity/row-XOR structure plus the printed
human-readable header echo, which is stronger than an 8-cell null shift; the
spectral canaries use ground-truth-spectrum / quiet-zone / red-channel /
GT-rendered controls as their discriminating statistic.

Canaries (report keys under 'canaries'):
  screening            (a) off-lattice spectral peaks in PRN fields vs the
                           GT-spectrum control (re-screening detector, §8-A)
  contone_fingerprint  (b) device screen freq/angle from setgray patches;
                           must NOT appear in imagemask patches (§8-B)
  toner_save           (c) K Dmax + in-solid periodic texture vs quiet zone (§8-C)
  clamp_phase          (d) 1-dot phase pairs ppV/ppH: quadrature delta
                           = 1.0 +- 0.2 dots vs GT-rendered control (§8-D)
  rescale              (e) absolute ruler/affine scale: >1% AND x~y agreement
                           => fit-to-page (§8-E)
  interpreter          (f) decoded strip PR/RE vs the expected engine (§8-G)
  mic                  (g) MIC hunt: quiet zone, color-scan blue channel,
                           high-pass + autocorrelation vs red-channel control

Entry point:
    run(scan_bw, scan_color, core_ctx=None) -> dict
payload shaped for cc.report_merge: {'canaries': {...}, 'selfreport': {...}}.
core_ctx (optional dict) may carry precomputed 'white_model_color'.

Determinism: this module uses NO randomness (all statistics are deterministic
functions of the scans + manifest).
K geometry is measured on the grey scan; color measurements (MIC blue/red,
C/M/Y densities, composite plane) on the color scan channels.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import cal_core as cc  # noqa: E402
import stripdec  # noqa: E402  (fixed v2 decoder, this experiment)

MM_PER_INCH = 25.4
PX_PER_MM = cc.SCAN_DPI / MM_PER_INCH  # 47.24 scan px per mm

# printed header echo of the CAL-1 page (verified by eye from the scan) —
# the reference for the interpreter canary and the selfreport cross-check.
HEADER_ECHO_REF = {
    "LAY": "1", "J": "2b7b26b5", "S": "paper-store/exp002-calpage",
    "R0": "600x600", "LL": "3", "RD": "600x600", "RE": "600x600",
    "PS": "595x842", "IB": "null", "PR": "HP Color LaserJet MFP M281fdw",
    "V": "3017", "RV": "1", "SN": "-1",
}
EXPECTED_ENGINE_SUBSTR = "M281"


# ---------------------------------------------------------------------------
# spectral helpers (rasters are on the half-dot grid, sub=2 -> d=0.5 dot/px)
# ---------------------------------------------------------------------------

def _hann2(shape: tuple[int, int]) -> np.ndarray:
    return np.outer(np.hanning(shape[0]), np.hanning(shape[1]))


def _excess_db(a: np.ndarray, med_size: int = 15
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(excess_db, fx, fy): 2-D magnitude spectrum in dB above its local
    median background (fftshifted). Frequencies in cycles/dot (d=0.5)."""
    a = np.asarray(a, np.float64)
    a = a - a.mean()
    mag = 20.0 * np.log10(np.abs(np.fft.fft2(a * _hann2(a.shape))) + 1e-9)
    mag = np.fft.fftshift(mag)
    bg = ndimage.median_filter(mag, size=med_size, mode="wrap")
    fy = np.fft.fftshift(np.fft.fftfreq(a.shape[0], d=0.5))
    fx = np.fft.fftshift(np.fft.fftfreq(a.shape[1], d=0.5))
    return mag - bg, fx, fy


def _freq_grids(fx: np.ndarray, fy: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    FX, FY = np.meshgrid(fx, fy)
    return FX, FY, np.hypot(FX, FY)


# ---------------------------------------------------------------------------
# (a) screening — PRN fields must show no off-GT narrowband peaks
# ---------------------------------------------------------------------------

def _lattice_bins(FX: np.ndarray, FY: np.ndarray, cell_dots: int,
                  tol: float = 0.012) -> np.ndarray:
    """Bins on the printed CELL lattice (fx AND fy near multiples of
    1/cell_dots). Dot gain outlines every cell boundary, so the PRINT has
    strong lines there that the ideal GT bitmap lacks (measured: +30.7 dB at
    (1/3, 0) on K/encode_c3) — that is the M7 self-clocking signal, expected
    channel behavior, NOT re-screening."""
    def near(F: np.ndarray) -> np.ndarray:
        return np.abs(F - np.round(F * cell_dots) / cell_dots) < tol
    return near(FX) & near(FY)


# measured scan-chain artifact: narrowband (+-0.5, ~0) cyc/dot (2-dot x
# period) present in the RAW (unresampled) grey scan inside K/solid at
# ~31 dB, absent in the quiet zone — dark-signal-dependent scanner/engine
# line, not a halftone screen (device screen is ~156 lpi, angled).
def _artifact_bins(FX: np.ndarray, FY: np.ndarray,
                   tol: float = 0.012) -> np.ndarray:
    return (np.abs(np.abs(FX) - 0.5) < tol) & (np.abs(FY) < tol)


def _screening_one(scan: dict, name: str) -> dict:
    v = cc.patch_view(scan, name)
    crop = v.crop()
    gt = cc.load_gt(v.entry)
    gt_raster = np.kron((1.0 - gt).astype(np.float32) * 255.0,
                        np.ones((v.sub, v.sub), np.float32))
    exc_p, fx, fy = _excess_db(crop)
    exc_g, _, _ = _excess_db(gt_raster)
    FX, FY, r = _freq_grids(fx, fy)
    base = (r > 0.04) & (r < 0.9)          # exclude DC/mottle + grid corners
    gt_peaks = ndimage.maximum_filter(exc_g, size=5) > 6.0
    lat = _lattice_bins(FX, FY, v.entry["params"]["cell_dots"])
    art = _artifact_bins(FX, FY)
    mask = base & ~gt_peaks & ~lat & ~art  # off-lattice, off-artifact bins
    stat = float(exc_p[mask].max())
    ctrl = float(exc_g[mask].max())        # analyzer artifact floor on GT
    i, j = np.unravel_index(int(np.argmax(np.where(mask, exc_p, -np.inf))),
                            exc_p.shape)
    return {"patch": name, "channel": v.reg_channel,
            "locked": bool(v.local_locked), "q": v.local_quality,
            "max_offgt_peak_db": stat, "gt_control_db": ctrl,
            "peak_freq_cyc_per_dot": [float(FX[i, j]), float(FY[i, j])],
            "cell_lattice_peak_db": float(exc_p[base & lat].max()),
            "scanchain_artifact_peak_db": float(exc_p[base & art].max()),
            "n_offgt_bins": int(mask.sum())}


def _path_fails(dets: list[dict]) -> bool:
    """A real screen is SYSTEMATIC: fail a path on one very strong peak
    (>=18 dB) or on >=12 dB peaks coherent (within 0.015 cyc/dot, sign-
    canonicalized) across two patches. Isolated 12-13 dB single bins are
    periodogram tail events, not screens."""
    if any(d["max_offgt_peak_db"] >= 18.0 for d in dets):
        return True
    strong = [d for d in dets if d["max_offgt_peak_db"] >= 12.0]
    for a in range(len(strong)):
        for b in range(a + 1, len(strong)):
            fa = np.abs(np.asarray(strong[a]["peak_freq_cyc_per_dot"]))
            fb = np.abs(np.asarray(strong[b]["peak_freq_cyc_per_dot"]))
            if float(np.hypot(*(fa - fb))) < 0.015:
                return True
    return False


def canary_screening(scan_bw: dict, scan_color: dict) -> dict:
    """Re-screening detector, split by emission path: single-plane imagemask
    patches (K grey + M green) vs put_cmyk_bitmap composites (DeviceCMYK
    1-bit/component `image` — the RIP treats those as color images)."""
    imagemask = [_screening_one(scan_bw, "K/encode_c3"),
                 _screening_one(scan_color, "M/encode_c3")]
    composite = [_screening_one(scan_color, "composite_c3_M"),
                 _screening_one(scan_color, "mottle_cmy_M")]
    details = {"imagemask_path": imagemask, "composite_path": composite}
    stat = max(d["max_offgt_peak_db"] for d in imagemask + composite)
    ctrl = max(d["gt_control_db"] for d in imagemask + composite)
    im_fail = _path_fails(imagemask)
    co_fail = _path_fails(composite)
    if not all(d["locked"] for d in imagemask + composite):
        status, note = "indeterminate", "not all screening patches locked"
    elif im_fail:
        status = "fail"
        status_note = "single-plane imagemask path re-screened"
        note = (f"{status_note}: coherent off-GT peaks up to "
                f"{max(d['max_offgt_peak_db'] for d in imagemask):.1f} dB "
                f"(GT control {ctrl:.1f} dB) — raw path compromised")
    elif co_fail:
        status = "fail"
        worst = max(composite, key=lambda d: d["max_offgt_peak_db"])
        note = (f"COMPOSITE path only: {worst['max_offgt_peak_db']:.1f} dB "
                f"off-GT peak at f=({worst['peak_freq_cyc_per_dot'][0]:+.3f},"
                f"{worst['peak_freq_cyc_per_dot'][1]:+.3f}) cyc/dot in "
                f"{worst['patch']} (plane-angle screen families, e.g. "
                f"~165 lpi @ +-14 deg, ~212 lpi @ 45 deg); single-plane "
                f"imagemask patches are clean (max "
                f"{max(d['max_offgt_peak_db'] for d in imagemask):.1f} dB, "
                f"no coherence) — put_cmyk_bitmap composites go through the "
                f"DeviceCMYK `image` color pipeline and ARE screened; the "
                f"imagemask raw path is intact (GT control {ctrl:.1f} dB)")
    else:
        status = "pass"
        note = (f"no coherent off-GT narrowband structure: max "
                f"{stat:.1f} dB single-bin vs GT control {ctrl:.1f} dB "
                f"(coherence rule; cell-lattice + scan-chain lines excluded "
                f"and reported in detail)")
    verdict = cc.canary_verdict("screening", status, stat, ctrl, note)
    verdict["detail"] = details
    return verdict


# ---------------------------------------------------------------------------
# (b) contone fingerprint — device screen must appear ONLY in setgray patches
# ---------------------------------------------------------------------------

def _dominant_peak(crop: np.ndarray) -> tuple[float, tuple[float, float]]:
    exc, fx, fy = _excess_db(crop)
    FX, FY, r = _freq_grids(fx, fy)
    m = (r > 0.05) & (r < 0.9)
    i, j = np.unravel_index(int(np.argmax(np.where(m, exc, -np.inf))), exc.shape)
    return float(exc[i, j]), (float(FX[i, j]), float(FY[i, j]))


def _excess_at(crop: np.ndarray, f_pk: tuple[float, float],
               tol: float = 0.02) -> float:
    """Max spectral excess within a freq disk around f_pk (and sign mirrors)."""
    exc, fx, fy = _excess_db(crop)
    FX, FY, _ = _freq_grids(fx, fy)
    best = -np.inf
    for sx in (1, -1):
        for sy in (1, -1):
            d = np.hypot(FX - sx * f_pk[0], FY - sy * f_pk[1])
            best = max(best, float(exc[d < tol].max()))
    return best


def canary_contone_fingerprint(scan_bw: dict) -> dict:
    """Extract the DEVICE halftone screen (freq/angle) from the setgray
    contone refs g25/g50/g75; assert it is absent from imagemask patches."""
    cont = {}
    for g in (75, 50, 25):
        v = cc.patch_view(scan_bw, f"contone_{g}")
        pk_db, f_pk = _dominant_peak(v.crop())
        f_mag = math.hypot(*f_pk)
        cont[g] = {"peak_db": pk_db, "freq_cyc_per_dot": list(f_pk),
                   "freq_mag": f_mag, "lpi": f_mag * cc.HW_DPI,
                   "angle_deg": math.degrees(math.atan2(f_pk[1], f_pk[0])),
                   "locked": bool(v.local_locked), "q": v.local_quality}
    # fingerprint = strongest contone peak; consistency across gray levels
    g_best = max(cont, key=lambda g: cont[g]["peak_db"])
    fp = cont[g_best]
    consistent = sum(abs(cont[g]["freq_mag"] - fp["freq_mag"])
                     < 0.15 * fp["freq_mag"] for g in cont)
    # leakage test with a matched-statistics control: the SAME disk-max
    # statistic on the GT raster of the same patch (single periodogram bins
    # over a random field reach ~10 dB above the local median by chance —
    # a bare 6 dB gate false-alarms; the GT control calibrates that floor).
    imask, imask_gt = {}, {}
    for name in ("K/density_50", "K/encode_c3"):
        v = cc.patch_view(scan_bw, name)
        gt = cc.load_gt(v.entry)
        gt_raster = np.kron((1.0 - gt).astype(np.float32) * 255.0,
                            np.ones((v.sub, v.sub), np.float32))
        imask[name] = _excess_at(v.crop(), tuple(fp["freq_cyc_per_dot"]))
        imask_gt[name] = _excess_at(gt_raster, tuple(fp["freq_cyc_per_dot"]))
    stat = max(imask.values())               # screen leakage into imagemask
    ctrl = max(imask_gt.values())            # chance floor of that statistic
    screen_db = fp["peak_db"]
    if screen_db < 10.0:
        status = "indeterminate"
        note = (f"no clear device screen in contone refs (max peak "
                f"{screen_db:.1f} dB < 10) — cannot fingerprint; imagemask "
                f"excess at that freq {stat:.1f} dB vs GT floor {ctrl:.1f}")
    elif stat < max(12.0, ctrl + 6.0):
        status = "pass"
        note = (f"device screen {fp['lpi']:.0f} lpi @ "
                f"{fp['angle_deg']:.1f} deg, {screen_db:.1f} dB in "
                f"contone_{g_best} (freq consistent in {consistent}/3 grays); "
                f"imagemask excess at screen freq {stat:.1f} dB vs GT chance "
                f"floor {ctrl:.1f} dB — bitmaps NOT contone-ized")
    else:
        status = "fail"
        note = (f"device screen ({fp['lpi']:.0f} lpi, {screen_db:.1f} dB) "
                f"ALSO in imagemask patches: {stat:.1f} dB vs GT floor "
                f"{ctrl:.1f} — raw path compromised")
    verdict = cc.canary_verdict("contone_fingerprint", status, stat, ctrl, note)
    verdict["detail"] = {"contone": cont, "fingerprint_from": f"contone_{g_best}",
                         "fingerprint": {"freq_cyc_per_dot": fp["freq_cyc_per_dot"],
                                         "lpi": fp["lpi"],
                                         "angle_deg": fp["angle_deg"],
                                         "strength_db": screen_db},
                         "imagemask_excess_db": imask,
                         "imagemask_gt_floor_db": imask_gt}
    return verdict


# ---------------------------------------------------------------------------
# (c) toner save — Dmax + in-solid periodic texture vs quiet-zone control
# ---------------------------------------------------------------------------

def _interior(a: np.ndarray, frac: float = 0.7) -> np.ndarray:
    h, w = a.shape
    mh, mw = int(h * (1 - frac) / 2), int(w * (1 - frac) / 2)
    return a[mh: h - mh, mw: w - mw]


def canary_toner_save(scan_bw: dict, scan_color: dict, wm: dict,
                      fingerprint: dict | None = None) -> dict:
    """Dmax + toner-save texture. The texture probe is evaluated AT the
    device-screen frequency (canary b fingerprint): toner-save modes dither
    solids with the device screen. A generic any-narrowband-peak test
    false-alarms on the measured (+-0.5, 0) cyc/dot scan-chain line (present
    in the RAW scan of the solid, 31 dB) — that line is reported as detail,
    not judged."""
    dens = {}
    for plane in ("K", "C", "M", "Y"):
        v = cc.patch_view(scan_color, f"{plane}/solid")
        d = cc.density(v, wm, channels=("r", "g", "b", "grey"))
        dens[plane] = {ch: float(np.median(_interior(d[ch])))
                       for ch in ("r", "g", "b", "grey")}
    dmax_k = dens["K"]["grey"]
    sol = _interior(cc.patch_view(scan_bw, "K/solid").crop(), 0.8)
    qz = cc.patch_view(scan_bw, "quiet_zone").crop()
    qz = qz[: sol.shape[0], : sol.shape[1]]
    detail: dict = {"solid_densities": dens}
    # generic top peaks (informative only)
    for lbl, a in (("solid", sol), ("quiet_zone", qz)):
        exc, fx, fy = _excess_db(a)
        FX, FY, r = _freq_grids(fx, fy)
        m = (r > 0.04) & (r < 0.9)
        i, j = np.unravel_index(int(np.argmax(np.where(m, exc, -np.inf))),
                                exc.shape)
        detail[f"{lbl}_top_peak"] = {
            "db": float(exc[i, j]),
            "freq_cyc_per_dot": [float(FX[i, j]), float(FY[i, j])]}
    detail["scanchain_artifact_note"] = (
        "solid top peak sits at (+-0.5, 0) cyc/dot = 2-dot x period, present "
        "in the RAW unresampled scan (~31 dB), absent in the quiet zone — "
        "dark-signal scan-chain line, not the 156-lpi device screen")
    if fingerprint is not None:
        f_pk = tuple(fingerprint["freq_cyc_per_dot"])
        tex_s = _excess_at(sol, f_pk)
        tex_q = _excess_at(qz, f_pk)
        detail["screenfreq_excess_db"] = {"solid": tex_s, "quiet_zone": tex_q}
    else:
        tex_s = tex_q = float("nan")
    if dmax_k < 1.1:
        status = "fail"
        why = f"K Dmax(grey) {dmax_k:.2f} < 1.1 (toner save / density servo)"
    elif fingerprint is None:
        status = "indeterminate"
        why = (f"K Dmax(grey) {dmax_k:.2f} ok but no device-screen "
               f"fingerprint available for the in-solid dither probe")
    elif tex_s > max(12.0, tex_q + 6.0):
        status = "fail"
        why = (f"device-screen-frequency texture inside K solid "
               f"{tex_s:.1f} dB vs quiet-zone {tex_q:.1f} dB — toner-save "
               f"dithering of solids")
    else:
        status = "pass"
        why = (f"K Dmax(grey) {dmax_k:.2f} >= 1.1; screen-freq texture in "
               f"solid {tex_s:.1f} dB vs quiet-zone control {tex_q:.1f} dB; "
               f"D(r,g,b) K=({dens['K']['r']:.2f},{dens['K']['g']:.2f},"
               f"{dens['K']['b']:.2f})")
    verdict = cc.canary_verdict(
        "toner_save", status, dmax_k,
        tex_q if fingerprint is not None else 0.0, note=why)
    verdict["detail"] = detail
    return verdict


# ---------------------------------------------------------------------------
# (d) clamp/interpolation — 1-dot phase pairs ppV / ppH
# ---------------------------------------------------------------------------

def _pair_delta(crop: np.ndarray, horizontal_lines: bool
                ) -> tuple[float, float, float]:
    """(delta_dots in [0,2), min_snr, min_depth) between the two pitch-2
    gratings of a phase_pair raster (sub=2: f0 = 0.25 cyc/px).
    Windows in dots: left [0,128), gap 14, right [142,270) along the
    modulation axis; phases measured in the COMMON coordinate, so the
    1-dot offset survives any common registration shift. depth = fundamental
    amplitude / 255 (fraction of full swing)."""
    a = np.asarray(crop, np.float64)
    prof = -(a.mean(axis=1) if horizontal_lines else a.mean(axis=0))
    prof = prof - prof.mean()
    x = np.arange(len(prof), dtype=np.float64)

    def phase_snr(sl: slice) -> tuple[float, float, float]:
        p, xx = prof[sl], x[sl]
        n = len(p) - (len(p) % 4)
        p, xx = p[:n], xx[:n]
        z = np.dot(p, np.exp(-2j * np.pi * 0.25 * xx))
        F = np.abs(np.fft.rfft(p * np.hanning(n)))
        k0 = int(round(0.25 * n))
        neigh = np.concatenate([F[max(1, k0 - 30): max(1, k0 - 2)],
                                F[k0 + 3: k0 + 31]])
        snr = float(F[k0] / (np.median(neigh) + 1e-9))
        depth = float(2.0 * np.abs(z) / n / 255.0)
        return float(np.angle(z)), snr, depth

    ph_l, snr_l, dep_l = phase_snr(slice(0, 256))
    ph_r, snr_r, dep_r = phase_snr(slice(284, 540))
    # dark-line position x0 satisfies angle(z) = -2*pi*f0*x0
    offset_px = -(ph_r - ph_l) / (2 * np.pi * 0.25)
    return float(offset_px / 2.0) % 2.0, min(snr_l, snr_r), min(dep_l, dep_r)


def canary_clamp_phase(scan_bw: dict) -> dict:
    detail = {}
    devs, snrs, depths = [], [], []
    for name, horiz in (("phasepair_v", False), ("phasepair_h", True)):
        v = cc.patch_view(scan_bw, name)
        delta, snr, depth = _pair_delta(v.crop(), horiz)
        gt = cc.nominal_bits(v.entry)
        gt_raster = np.kron((1.0 - gt) * 255.0, np.ones((2, 2)))
        delta_gt, _, _ = _pair_delta(gt_raster, horiz)
        detail[name] = {"delta_dots": delta, "delta_gt_dots": delta_gt,
                        "min_snr": snr, "min_mod_depth": depth,
                        "locked": bool(v.local_locked), "q": v.local_quality}
        devs.append(abs(delta - 1.0))
        snrs.append(snr)
        depths.append(depth)
    # statistic = the delta furthest from 1.0; control = GT-rendered delta
    worst = max(detail.values(), key=lambda d: abs(d["delta_dots"] - 1.0))
    stat = worst["delta_dots"]
    ctrl = worst["delta_gt_dots"]
    min_snr, min_depth = min(snrs), min(depths)
    if min_depth < 0.03 or min_snr < 4.0:
        status = "indeterminate"
        note = (f"pitch-2 grating modulation depth {min_depth * 100:.1f}% of "
                f"full swing (SNR {min_snr:.1f}) — gratings develop to "
                f"near-uniform mush (consistent with the settled 001 Nyquist "
                f"1-on/1-off closure): phase delta unmeasurable, residual "
                f"signal is resample moire (deltas "
                + ", ".join(f"{k}={d['delta_dots']:.2f}" for k, d in detail.items())
                + f"; GT-rendered control {ctrl:.2f} confirms the estimator)")
    elif max(devs) <= 0.2:
        status = "pass"
        note = (f"quadrature deltas within 1.0+-0.2 dots: "
                + ", ".join(f"{k}={d['delta_dots']:.2f}" for k, d in detail.items())
                + f" (GT control {ctrl:.2f}); depth {min_depth * 100:.0f}%")
    else:
        status = "fail"
        note = (f"phase delta {stat:.2f} dots deviates >0.2 from 1.0 at "
                f"depth {min_depth * 100:.0f}%, SNR {min_snr:.1f} — "
                f"resolution clamp / re-rendering to a coarser grid")
    verdict = cc.canary_verdict("clamp_phase", status, stat, ctrl, note)
    verdict["detail"] = detail
    return verdict


# ---------------------------------------------------------------------------
# (e) rescale — absolute scale from affine + ruler ticks
# ---------------------------------------------------------------------------

def _ruler_pitch_corr(scan: dict, which: str) -> dict:
    """Measured ruler tick pitch in the affine-warped frame / nominal (120 px).
    A correction of 1.0 means the affine already captures the true printed
    pitch; the absolute page scale is then px_per_dot / 2.0 exactly."""
    e = cc.entry(scan["manifest"], f"ruler_{which}")
    if which == "top":
        n_ticks, w = 75, 74 * 60 + 3
        band = cc.warp_channel(scan, "grey", e["x_dots"], e["y_dots"] + 6, w, 12)
        prof = (255.0 - band).mean(axis=0)
    else:
        n_ticks, h = 96, 95 * 60 + 3
        band = cc.warp_channel(scan, "grey", e["x_dots"] + 6, e["y_dots"], 12, h)
        prof = (255.0 - band).mean(axis=1)
    wgt = np.clip(prof - np.median(prof), 0.0, None)
    centers, idx = [], []
    for i in range(n_ticks):
        c0 = 120 * i + 3
        lo, hi = c0 - 30, c0 + 31
        if lo < 0 or hi > len(prof):
            continue
        ww = wgt[lo:hi]
        if ww.sum() < 10.0:
            continue
        centers.append(float((ww * np.arange(lo, hi)).sum() / ww.sum()))
        idx.append(i)
    p = np.polyfit(idx, centers, 1)
    resid = np.array(centers) - np.polyval(p, idx)
    return {"pitch_px": float(p[0]), "corr": float(p[0] / 120.0),
            "n_ticks": len(idx),
            "resid_rms_px": float(np.sqrt(np.mean(resid ** 2)))}


def canary_rescale(scan_bw: dict, scan_color: dict) -> dict:
    detail = {}
    for tag, scan in (("bw", scan_bw), ("color", scan_color)):
        reg = scan["registration"]
        rt = _ruler_pitch_corr(scan, "top")
        rl = _ruler_pitch_corr(scan, "left")
        sx = reg["px_per_dot_x"] / cc.PX_PER_DOT * rt["corr"]
        sy = reg["px_per_dot_y"] / cc.PX_PER_DOT * rl["corr"]
        detail[tag] = {"scale_x": sx, "scale_y": sy,
                       "dev_x_pct": (sx - 1) * 100, "dev_y_pct": (sy - 1) * 100,
                       "ruler_top": rt, "ruler_left": rl}
    d = detail["bw"]
    stat = max(abs(d["dev_x_pct"]), abs(d["dev_y_pct"]))
    ctrl = abs(d["dev_x_pct"] - d["dev_y_pct"])
    if stat > 1.0 and ctrl < 0.2:
        status = "fail"
        note = (f"uniform scale deviation {stat:.2f}% with x~y agreement "
                f"{ctrl:.2f}% — fit-to-page/rescale in the print path")
    elif stat <= 1.0:
        status = "pass"
        note = (f"scale dev x {d['dev_x_pct']:+.3f}% y {d['dev_y_pct']:+.3f}% "
                f"(flag >1% uniform); within hygro envelope (+-0.3%/day, "
                f"001); color-scan y differs by "
                f"{detail['color']['dev_y_pct'] - d['dev_y_pct']:+.3f}% "
                f"(scanner transport / hygro between scans)")
    else:
        status = "indeterminate"
        note = (f"scale deviation {stat:.2f}% but anisotropic "
                f"(|x-y| {ctrl:.2f}%) — hygro/fuser shrink, not fit-to-page")
    verdict = cc.canary_verdict("rescale", status, stat, ctrl, note)
    verdict["detail"] = detail
    return verdict


# ---------------------------------------------------------------------------
# (f) interpreter fingerprint + selfreport — machine strips
# ---------------------------------------------------------------------------

def decode_strips(scan_bw: dict) -> tuple[list[dict], dict]:
    strips = stripdec.decode_image(scan_bw["grey"])
    summary = []
    fields: dict[str, str] = {}
    for s in strips:
        summary.append({
            "crc_ok": bool(s["crc_ok"]), "magic_ok": bool(s["magic_ok"]),
            "clock_score": float(s["clock_score"]),
            "module_px": [float(s["module_px"][0]), float(s["module_px"][1])],
            "skew_deg": float(s["skew_deg"]),
            "sync_errors": s["sync_errors"], "parity_errors": s["parity_errors"],
            "rowxor_errors": s["rowxor_errors"],
            "rotated_180": bool(s["rotated_180"]),
        })
        if s["crc_ok"] and not fields:
            fields = dict(s["fields"])
    return summary, fields


def canary_interpreter(strips_summary: list[dict], fields: dict) -> dict:
    n_crc = sum(s["crc_ok"] for s in strips_summary)
    ctrl = n_crc / 2.0
    if not fields:
        verdict = cc.canary_verdict(
            "interpreter", "indeterminate", 0.0, ctrl,
            note=f"no CRC-valid strip decoded ({len(strips_summary)} found)")
        verdict["detail"] = {"strips": strips_summary}
        return verdict
    matches = {k: fields.get(k, "").strip() == v
               for k, v in HEADER_ECHO_REF.items()}
    stat = sum(matches.values()) / len(HEADER_ECHO_REF)
    pr = fields.get("PR", "")
    ghost = "ghostscript" in pr.lower()
    engine_ok = EXPECTED_ENGINE_SUBSTR in pr
    res_ok = (fields.get("RE", "").strip() == HEADER_ECHO_REF["R0"]
              and fields.get("RD", "").strip() == HEADER_ECHO_REF["R0"])
    if ghost or not engine_ok:
        status = "fail"
        note = (f"PR={pr!r} is not the expected engine "
                f"({EXPECTED_ENGINE_SUBSTR}) — job re-rasterized upstream?")
    elif not res_ok:
        status = "fail"
        note = (f"granted resolution RD={fields.get('RD')} RE={fields.get('RE')} "
                f"!= requested {HEADER_ECHO_REF['R0']}")
    elif stat == 1.0 and n_crc == 2:
        status = "pass"
        note = (f"both strips CRC-ok; all {len(HEADER_ECHO_REF)} payload fields "
                f"match the printed header echo; PR={pr.strip()!r}, "
                f"RE={fields['RE']} as requested; PS interpreter LL="
                f"{fields.get('LL')} executed ON the device")
    else:
        status = "indeterminate"
        bad = [k for k, v in matches.items() if not v]
        note = f"decoded but fields {bad} differ from header echo; crc strips {n_crc}/2"
    verdict = cc.canary_verdict("interpreter", status, stat, ctrl, note)
    verdict["detail"] = {"fields": fields, "field_matches": matches}
    return verdict


# ---------------------------------------------------------------------------
# (g) MIC hunt — quiet zone, blue channel, high-pass + autocorrelation
# ---------------------------------------------------------------------------

def _autocorr_peak(a: np.ndarray, min_lag_px: int = 40) -> dict:
    hp = a - ndimage.gaussian_filter(a, 8.0)
    F = np.fft.fft2(hp * _hann2(hp.shape))
    ac = np.fft.fftshift(np.fft.ifft2(np.abs(F) ** 2).real)
    ac = ac / ac[ac.shape[0] // 2, ac.shape[1] // 2]
    cy, cx = ac.shape[0] // 2, ac.shape[1] // 2
    Y, X = np.ogrid[: ac.shape[0], : ac.shape[1]]
    rr = np.hypot(Y - cy, X - cx)
    ann = (rr >= min_lag_px) & (rr <= min(cy, cx) - 8)
    vals = ac[ann]
    med = float(np.median(vals))
    sigma = 1.4826 * float(np.median(np.abs(vals - med))) + 1e-12
    k = int(np.argmax(np.where(ann, ac, -np.inf)))
    i, j = np.unravel_index(k, ac.shape)
    peak = float(ac[i, j])
    return {"peak": peak, "z": (peak - med) / sigma,
            "lag_px": [int(i - cy), int(j - cx)],
            "lag_mm": [float((i - cy) / PX_PER_MM), float((j - cx) / PX_PER_MM)],
            "sigma": sigma, "ac": ac, "hp": hp, "ann": ann}


def canary_mic(scan_color: dict) -> dict:
    v = cc.patch_view(scan_color, "quiet_zone")
    trim = 40
    blue = v.crop("b").astype(np.float64)[trim:-trim, trim:-trim]
    red = v.crop("r").astype(np.float64)[trim:-trim, trim:-trim]
    rb = _autocorr_peak(blue)
    rr_ = _autocorr_peak(red)
    # red control AT the blue peak lag (paper texture is common-mode)
    cy, cx = rr_["ac"].shape[0] // 2, rr_["ac"].shape[1] // 2
    dy, dx = rb["lag_px"]
    red_at_blue = float(rr_["ac"][cy + dy, cx + dx])
    stat, ctrl = rb["z"], rr_["z"]
    found = stat > 6.0 and rb["peak"] > 2.0 * max(red_at_blue, 3.0 * rr_["sigma"])
    detail = {
        "blue": {k: rb[k] for k in ("peak", "z", "lag_px", "lag_mm", "sigma")},
        "red": {k: rr_[k] for k in ("peak", "z", "lag_px", "lag_mm", "sigma")},
        "red_ac_at_blue_lag": red_at_blue,
        "region": "quiet_zone 28x28 mm (periods >14 mm not detectable)",
    }
    if found:
        # map the tile: dot blobs = strong blue dips absent in red
        hp = rb["hp"]
        s = float(hp.std())
        mask = hp < -4.0 * s
        lbl, n = ndimage.label(mask)
        areas = ndimage.sum_labels(mask, lbl, np.arange(1, n + 1))
        areas = areas[areas >= 3]
        area_mm2 = (blue.shape[0] / PX_PER_MM) * (blue.shape[1] / PX_PER_MM)
        detail["mic_map"] = {
            "period_mm": [abs(rb["lag_mm"][0]), abs(rb["lag_mm"][1])],
            "period_dots": [abs(rb["lag_px"][0]) / 2.0, abs(rb["lag_px"][1]) / 2.0],
            "n_dots": int(len(areas)),
            "dots_per_mm2": float(len(areas) / area_mm2),
            "median_dot_area_dots2": float(np.median(areas) / 4.0) if len(areas) else 0.0,
        }
        status = "fail"   # = MIC tile FOUND: Y plane is contaminated (§2.4)
        note = (f"periodic BLUE-ONLY structure: autocorr z={stat:.1f} at lag "
                f"({rb['lag_mm'][0]:+.2f},{rb['lag_mm'][1]:+.2f}) mm, peak "
                f"{rb['peak']:.3f} vs red-at-same-lag {red_at_blue:.3f} — "
                f"MIC map in detail. 'fail' = tracking dots present "
                f"(a finding about the channel, not the analyzer)")
    elif rb["peak"] <= 2.0 * red_at_blue or stat <= 1.5 * ctrl:
        # blue structure is common-mode paper/scanner texture: the red
        # channel (blind to yellow) shows comparable or stronger correlation
        status = "pass"
        note = (f"no yellow-specific structure: blue autocorr peak "
                f"{rb['peak']:.3f} (z={stat:.1f}) vs red control z={ctrl:.1f} "
                f"and red@blue-lag {red_at_blue:.3f} — common-mode texture, "
                f"not a MIC tile (period <=14 mm, quiet-zone sensitivity)")
    else:
        status = "indeterminate"
        note = (f"blue autocorr z={stat:.1f} above red control z={ctrl:.1f} "
                f"but below the found gate (peak {rb['peak']:.3f}, "
                f"red@blue-lag {red_at_blue:.3f}) — weak/ambiguous "
                f"periodicity, larger blank area needed")
    verdict = cc.canary_verdict("mic", status, stat, ctrl, note)
    verdict["detail"] = detail
    return verdict


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def run(scan_bw: dict, scan_color: dict, core_ctx: dict | None = None) -> dict:
    """All seven canaries + strip selfreport. Scans must be (or will be)
    registered. Returns a payload for cc.report_merge."""
    core_ctx = core_ctx or {}
    for scan in (scan_bw, scan_color):
        if scan.get("registration") is None:
            cc.register(scan)
    wm = core_ctx.get("white_model_color") or cc.white_model(scan_color)

    strips_summary, fields = decode_strips(scan_bw)
    echo_match = bool(fields) and all(
        fields.get(k, "").strip() == v for k, v in HEADER_ECHO_REF.items())

    contone = canary_contone_fingerprint(scan_bw)
    fingerprint = (contone["detail"]["fingerprint"]
                   if contone["detail"]["fingerprint"]["strength_db"] >= 10.0
                   else None)
    canaries = {
        "screening": canary_screening(scan_bw, scan_color),
        "contone_fingerprint": contone,
        "toner_save": canary_toner_save(scan_bw, scan_color, wm, fingerprint),
        "clamp_phase": canary_clamp_phase(scan_bw),
        "rescale": canary_rescale(scan_bw, scan_color),
        "interpreter": canary_interpreter(strips_summary, fields),
        "mic": canary_mic(scan_color),
    }
    selfreport = {
        "strips": strips_summary,
        "n_strips_crc_ok": sum(s["crc_ok"] for s in strips_summary),
        "payload_fields": fields,
        "payload_matches_header_echo": echo_match,
        "jobid_matches_manifest": bool(
            fields.get("J") == scan_bw["manifest"]["jobid"]),
        "seed_matches_manifest": bool(
            fields.get("S") == scan_bw["manifest"]["seed"]),
        "decoder": "stripdec v2 (skew-tolerant border lines + clock-pair "
                   "quadrature column tracking + per-row centroid refinement)",
    }
    return {"canaries": canaries, "selfreport": selfreport}


# ---------------------------------------------------------------------------
# smoke run on the real scans
# ---------------------------------------------------------------------------

def _fmt_verdict(v: dict) -> str:
    return (f"{v['name']:<20} {v['status']:<13} stat={v['statistic']:9.3f} "
            f"ctrl={v['control']:9.3f}  {v['note']}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="canary family smoke run")
    # the run's scans: scans/test-scan-calpage-{bw,color}.png
    ap.add_argument("scan_bw")
    ap.add_argument("scan_color")
    ap.add_argument("--out", default=str(cc.BUILD / "cal_canary_report.json"))
    args = ap.parse_args()

    print("loading + registering scans ...")
    scan_bw = cc.load_scan(args.scan_bw)
    cc.register(scan_bw)
    scan_color = cc.load_scan(args.scan_color)
    cc.register(scan_color)
    print(f"bw   residual RMS {scan_bw['registration']['residual_rms_dots']:.3f} dots, "
          f"color {scan_color['registration']['residual_rms_dots']:.3f} dots")

    payload = run(scan_bw, scan_color)

    print("\n== canaries ==")
    for v in payload["canaries"].values():
        print(_fmt_verdict(v))
    print("\n== selfreport ==")
    sr = payload["selfreport"]
    print(f"strips crc ok: {sr['n_strips_crc_ok']}/2   "
          f"header echo match: {sr['payload_matches_header_echo']}   "
          f"jobid match: {sr['jobid_matches_manifest']}")
    for k, val in sr["payload_fields"].items():
        print(f"   {k} = {val}")

    rep = cc.report_init(scan_bw)
    cc.report_merge(rep, payload)
    cc.save_report(rep, args.out)
    print(f"\nreport -> {args.out}")

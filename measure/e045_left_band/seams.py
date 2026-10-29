"""e045 — the scanner's common-x seam lattice (§045.4), read WITHOUT ground truth from any capture of a printed
cell field (K or colour, any cell pitch, any page orientation on the platen).

Method.  Scan columns are the sensor axis; a seam is a platen-fixed column boundary where the whole image jumps in x.
  1. edge energy: per block of BLOCK_MM of scan rows (short enough that page rotation cannot smear a cell
     boundary) and per channel, the row sum of |I(r, c + 1) - I(r, c)|;
  2. the seams: the column edge energy (all blocks and channels) over its SPIKE_MED_MM running median, in robust z
     (z >= SPIKE_Z); the spike marks a column boundary of the scanner in level and noise — it stands on bare paper
     too (refuter, 2026-10-12: ratio 2.4-2.9 on sheet 3's blank gaps, column-mean steps up to 1.5 levels) — so it
     LOCATES the seam and says nothing of the jump's width (`spike_width_px` is the spike's); the lattice (T, first
     column) = the period in PERIOD_MM and phase scoring most spikes on it minus lattice columns over printed
     content without one, refitted by least squares;
  3. the jump: the cell pitch P = cell_dots * dpi / 600 px refined from the summed per-block power (+/- 3 %, then
     +/- 0.05 %, parabolic; `--cell-dots auto` = the largest of CELL_CANDIDATES whose peak stands AUTO_SNR over
     its band); complex demodulation at 1 / P, every block high-passed by its one-pitch running mean, its phase
     (page rotation, y wander) removed by aligning it on a REF_MM-smoothed reference (three iterations, blocks
     weighted by coherent amplitude), the blocks summed; the channels aligned on the strongest by their
     REF-smoothed phase difference and summed; x_off(c) = -arg(box_W sum) / (2 pi / P) in scan px (+ = content
     displaced to larger columns; W = WINDOW_MM), unwrapped over the columns with printed content, detrended;
     per seam J = right line - left line at the seam (FIT_LEN_MM beyond FIT_GAP_MM), per channel too.  Phase fixes
     J only modulo one pitch: every jump is put on the branch of the jumps' circular mean (`branch_margin_px` =
     how far that mean sits from +/- P / 2; c3 and coarser rows settle the branch where c2 is tight);
  4. between seams: one common slope with a free jump per seam over the detrended profile (seams masked), against
     the mean J / T — a consistency check only: x_off is measured against the capture's own mean pitch, so the
     slope equals -J / T by construction and does not separate the scanner's scale from the printer's; the profile folded on the lattice (FOLD_BIN_MM bins, median); the step statistic's own fold
     (STEP_GAP_MM, STEP_LEN_MM) as a phase-only cross-check of the period.
`cost`: sheet 3 re-read per cell (cells.py: the readout's windows, the neighbour-prior windows, the cross-fitted
sub-windows), band colour tables (slices.predict), error per cell column minus the band's own level at
|d| >= 4 mm in the same seam period, binned by the signed distance d to the nearest seam (scan columns through
the readout's page affine); the window and sub-window errors of sheet3.py's CSVs the same way.

    PYTHONPATH=src:. env/bin/python -u -m measure.e045_left_band.seams detect \\
        --scan <capture.tiff> --label <name> --out <dir> [--cell-dots 2|auto] [--date D] [--orientation O]
    ... seams archive --capture <published_path in the archive's MANIFEST.tsv> --label <name> --out <dir> [...]
        (rebuilds the TIFF under --tmp with the archive's tools/unpack.sh, checks sha256_raw, detects, deletes it)
    ... seams table --out <dir>                       (seams.csv + seams.json from every <label>.json in <dir>)
    ... seams cost --sheet3-dir <scratch/e045/sheet3> --scan <sheet 3 TIFF> --manifest <..> --gt <..>
        --summary <..> --seams-json <sheet 3's <label>.json> --out <dir> [--workers 8] [--bands B1,..]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np
import tifffile
from scipy import ndimage

PRINT_DPI = 600.0
MM_PER_IN = 25.4
BLOCK_MM = 0.34
WINDOW_MM = 0.5
REF_MM = 5.0
VALID_FRAC = 0.25
STEP_GAP_MM = 0.4
STEP_LEN_MM = 1.5
PERIOD_MM = (6.0, 40.0)
PERIOD_STEP_MM = 0.01
FIT_GAP_MM = 0.6
FIT_LEN_MM = 4.0
FOLD_BIN_MM = 0.2
LATTICE_BIN_MM = 0.5
FOLD_KEEP = 0.8
CELL_CANDIDATES = (2, 3, 4, 6)
AUTO_SNR = 30.0
SPIKE_Z = 12.0
SPIKE_MED_MM = 0.5
SPIKE_TOL_PX = 2
LATTICE_MIN_SEAMS = 3
ARCHIVE = Path("<home>/src/evidence/paper-store-evidence-holo-2026-10")
Rec = dict[str, Any]


def open_capture(path: Path, dpi: float | None) -> tuple[np.ndarray, float]:
    """The capture as a read-only memmap (rows, cols[, ch]) and its dpi (the tag unless given)."""
    with tifffile.TiffFile(path) as tf:
        tag = tf.pages[0].tags.get("XResolution")
        tag_dpi = float(tag.value[0]) / float(tag.value[1]) if tag else None
    img = tifffile.memmap(path, mode="r")
    return img, float(dpi or tag_dpi)


def edge_profiles(img: np.ndarray, rows_per_block: int) -> np.ndarray:
    """(channels, blocks, cols - 1) float32: per block of rows the row sum of |horizontal difference|."""
    h, w = img.shape[:2]
    nch = 1 if img.ndim == 2 else min(img.shape[2], 3)
    nb = h // rows_per_block
    E = np.empty((nch, nb, w - 1), np.float32)
    for b in range(nb):
        blk = np.asarray(img[b * rows_per_block:(b + 1) * rows_per_block])
        for k in range(nch):
            ch = (blk if blk.ndim == 2 else blk[..., k]).astype(np.int16)
            E[k, b] = np.abs(np.diff(ch, axis=1)).sum(0, dtype=np.int32)
    return E


def band_power(E: np.ndarray, freqs: np.ndarray) -> np.ndarray:
    """Summed over channels and blocks: |sum_c (E - block mean) exp(-2 pi i f c)|^2 per frequency (cycles/px)."""
    c = np.arange(E.shape[-1])
    M = np.exp(-2j * np.pi * np.outer(c, freqs)).astype(np.complex64)
    out = np.zeros(len(freqs))
    for Ek in E:
        X = (Ek - Ek.mean(1, keepdims=True)).astype(np.complex64) @ M
        out += (np.abs(X.astype(np.complex128)) ** 2).sum(0)
    return out


def peak(E: np.ndarray, f_nom: float) -> tuple[float, float]:
    """(refined frequency, peak / band median) near f_nom."""
    coarse = f_nom * (1 + np.linspace(-0.03, 0.03, 241))
    pw = band_power(E, coarse)
    f0 = coarse[int(np.argmax(pw))]
    fine = f0 * (1 + np.linspace(-0.0005, 0.0005, 101))
    pf = band_power(E, fine)
    i = int(np.clip(np.argmax(pf), 1, len(fine) - 2))
    a, b, c = np.log(pf[i - 1:i + 2])
    d = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) < 0 else 0.0
    return float(fine[i] + d * (fine[1] - fine[0])), float(pw.max() / np.median(pw))


def coherent(Ek: np.ndarray, f: float, pitch_px: float, ref_px: int) -> np.ndarray:
    """S(c) = sum_b m_b(c) conj(u_b): the blocks' demodulated profiles phase-aligned and amplitude-weighted."""
    hp = Ek - ndimage.uniform_filter1d(Ek, max(2, int(round(pitch_px))), axis=1, mode="nearest")
    carrier = np.exp(-2j * np.pi * f * np.arange(Ek.shape[1])).astype(np.complex64)
    m = hp.astype(np.complex64) * carrier
    u = m.sum(1)
    for _ in range(3):
        S = (m * np.conj(u)[:, None]).sum(0)
        R = box(S, ref_px)
        R = R / np.maximum(np.abs(R), 1e-12)
        u = m @ np.conj(R).astype(np.complex64)
    return (m * np.conj(u)[:, None]).sum(0).astype(np.complex128)


def box(z: np.ndarray, n: int) -> np.ndarray:
    n = max(1, int(n))
    if np.iscomplexobj(z):
        return ndimage.uniform_filter1d(z.real, n, mode="nearest") + 1j * ndimage.uniform_filter1d(z.imag, n, mode="nearest")
    return ndimage.uniform_filter1d(z, n, mode="nearest")


def profiles(S: list[np.ndarray], f: float, n: int, ref_px: int) -> Rec:
    """The channels' box_n S aligned on the strongest by their REF-smoothed phase difference (per-plane registration
    is slow; a seam is common to every channel) and summed (each over its own 90th-percentile amplitude); x_off of
    the sum unwrapped over the valid columns (box |S| above VALID_FRAC of its 90th percentile, which a seam inside
    the box does not cancel) and linearly detrended (`trend` = the removed slope, px per px); per channel x_off =
    the sum's plus the channel's (small) phase difference from it."""
    Z = [box(s, n) for s in S]
    A = [box(np.abs(s), max(n, 2 * int(round(1.0 / f)))) for s in S]
    norm = [np.percentile(a, 90) for a in A]
    ref = int(np.argmax(norm))
    tot = np.zeros(len(Z[0]), complex)
    rot = []
    for z, nm in zip(Z, norm):
        d = box(z * np.conj(Z[ref]) / np.maximum(np.abs(z) * np.abs(Z[ref]), 1e-12), ref_px)
        rot.append(np.exp(-1j * np.angle(d)))
        tot += z * rot[-1] / nm
    amp = sum(a / nm for a, nm in zip(A, norm))
    valid = amp > VALID_FRAC * np.percentile(amp, 90)
    idx = np.flatnonzero(valid)
    x = np.full(len(tot), np.nan)
    x[idx] = -np.unwrap(np.angle(tot[idx])) / (2 * np.pi * f)
    p = np.polyfit(idx, x[idx], 1, w=amp[idx])
    x[idx] -= np.polyval(p, idx)
    xch = [x - np.angle(z * r * np.conj(tot)) / (2 * np.pi * f) for z, r in zip(Z, rot)]
    return {"x": x, "w": np.where(valid, amp ** 2, 0.0), "x_ch": xch, "trend": float(p[0])}


def rebranch(x: np.ndarray, seams_col: list[float], jumps: list[float], pitch: float) -> tuple[np.ndarray, float]:
    """Every jump moved by whole pitches onto the branch of the jumps' circular mean (the phase fixes a jump only
    modulo one pitch; the unwrap takes the shorter arc seam by seam); returns the corrected profile and that mean."""
    ang = np.exp(2j * np.pi * np.asarray(jumps) / pitch)
    ref = float(np.angle(ang.mean()) / (2 * np.pi) * pitch)
    out = x.copy()
    c = np.arange(len(x))
    for cs, J in zip(seams_col, jumps):
        k = round((ref - J) / pitch)
        if k:
            out[c > cs] += k * pitch
    return out, ref


def detrend(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    idx = np.flatnonzero((w > 0) & np.isfinite(x))
    p = np.polyfit(idx, x[idx], 1, w=np.sqrt(w[idx]))
    return x - np.polyval(p, np.arange(len(x)))


def wmean_window(x: np.ndarray, w: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    xw = np.concatenate([[0.0], np.cumsum(np.nan_to_num(x) * w)])
    ws = np.concatenate([[0.0], np.cumsum(w)])
    lo, hi = np.clip(lo, 0, len(x)), np.clip(hi, 0, len(x))
    d = ws[hi] - ws[lo]
    return np.where(d > 0, (xw[hi] - xw[lo]) / np.maximum(d, 1e-12), np.nan)


def step_stat(x: np.ndarray, w: np.ndarray, gap: int, length: int) -> np.ndarray:
    c = np.arange(len(x))
    right = wmean_window(x, w, c + gap, c + gap + length)
    left = wmean_window(x, w, c - gap - length, c - gap)
    cover = wmean_window(np.ones(len(x)), (w > 0).astype(float), c - gap - length, c + gap + length)
    s = right - left
    return np.where(np.nan_to_num(cover) > 0.8, s, np.nan)


def fold_score(s: np.ndarray, px_mm: float, bin_px: float) -> Rec:
    """The lattice (T, c0) over PERIOD_MM from the fold of |s| (|s|: a jump near half a pitch has an ambiguous
    sign): per T the fold's peak above its median; T = the SHORTEST period whose peak reaches FOLD_KEEP of the
    best (a multiple of the period folds as high, a fraction lower); z = that peak over the fold's robust spread
    away from the peak; the sign = that of the mean s in the peak bin."""
    c = np.flatnonzero(np.isfinite(s)).astype(float)
    v = s[c.astype(int)]
    av = np.abs(v)
    res = []
    for T_mm in np.arange(PERIOD_MM[0], PERIOD_MM[1], PERIOD_STEP_MM):
        T = T_mm * px_mm
        nbin = max(8, int(T / bin_px))
        k = ((c % T) / T * nbin).astype(int) % nbin
        cnt = np.maximum(np.bincount(k, minlength=nbin), 1)
        fold = np.bincount(k, av, minlength=nbin) / cnt
        j = int(np.argmax(fold))
        res.append((T, fold, j, k, nbin))
    peaks = np.array([f[j] - np.median(f) for _, f, j, _, _ in res])
    i = int(np.flatnonzero(peaks >= FOLD_KEEP * peaks.max())[0])
    T, fold, j, k, nbin = res[i]
    away = np.abs((np.arange(nbin) - j + nbin // 2) % nbin - nbin // 2) > max(2, nbin // 10)
    med = np.median(fold[away])
    mad = 1.4826 * np.median(np.abs(fold[away] - med)) + 1e-12
    return {"z": float((fold[j] - med) / mad), "T_px": float(T), "c0": float((j + 0.5) / nbin * T),
            "sign": float(np.sign(np.bincount(k, v, minlength=nbin)[j])), "fold_peak_px": float(fold[j] - med),
            "peak_vs_best": float(peaks[i] / peaks.max()), "best_T_px": float(res[int(np.argmax(peaks))][0])}


def line_jump(x: np.ndarray, w: np.ndarray, cs: float, gap: int, length: int) -> float:
    def fit(lo: int, hi: int) -> np.ndarray | None:
        lo, hi = max(lo, 0), min(hi, len(x))
        idx = np.arange(lo, hi)
        ok = idx[(w[lo:hi] > 0) & np.isfinite(x[lo:hi])]
        if len(ok) < 0.5 * length:
            return None
        return np.polyfit(ok, x[ok], 1)
    L, R = fit(int(cs - gap - length), int(cs - gap)), fit(int(cs + gap), int(cs + gap + length))
    if L is None or R is None:
        return float("nan")
    return float(np.polyval(R, cs) - np.polyval(L, cs))


def spike_profile(E: np.ndarray, px_mm: float) -> np.ndarray:
    """Robust z per column of the column edge energy (channels and blocks summed) over its running median of
    SPIKE_MED_MM: the seam's column boundary in level and noise (on bare paper as on content)."""
    e = E.sum((0, 1)).astype(np.float64)
    r = e / np.maximum(ndimage.median_filter(e, size=int(SPIKE_MED_MM * px_mm) | 1, mode="nearest"), 1e-9)
    med = np.median(r)
    return (r - med) / (1.4826 * np.median(np.abs(r - med)) + 1e-12)


def spike_lattice(z: np.ndarray, valid: np.ndarray, px_mm: float) -> Rec:
    """Columns with z >= SPIKE_Z (one per run); the period T in PERIOD_MM and phase c0 with the best score = spikes
    on the lattice (within SPIKE_TOL_PX) minus lattice columns inside the measured columns (`valid`) where z stays
    under SPIKE_Z / 3 (a fraction of the period is penalised by its empty columns, a multiple by the spikes it
    misses); refitted by least squares."""
    hot = np.flatnonzero(z >= SPIKE_Z)
    peaks: list[int] = []
    for c in hot:
        if peaks and c - peaks[-1] <= 3:
            if z[c] > z[peaks[-1]]:
                peaks[-1] = int(c)
            continue
        peaks.append(int(c))
    P = np.array(peaks, float)
    if len(P) < 2:
        return {"spikes": peaks, "found": False}
    lo, hi = PERIOD_MM[0] * px_mm, PERIOD_MM[1] * px_mm
    cands = sorted({d / m for i in range(len(P)) for d in P[i + 1:] - P[i] for m in range(1, int(d / lo) + 1)
                    if lo <= d / m <= hi})
    zmax = ndimage.maximum_filter1d(z, 2 * SPIKE_TOL_PX + 1, mode="nearest")
    scored = []
    for T in cands:
        best = (-np.inf, 0.0)
        for c0 in P:
            ph = (P - c0 + T / 2) % T - T / 2
            n = int((np.abs(ph) <= SPIKE_TOL_PX).sum())
            lc = np.round(c0 - np.floor(c0 / T) * T + np.arange(int(len(z) / T) + 1) * T).astype(int)
            lc = lc[lc < len(z)]
            miss = int((valid[lc] & (zmax[lc] < SPIKE_Z / 3)).sum())
            if n - miss > best[0]:
                best = (n - miss, float(c0))
        scored.append((T, *best))
    T, n, c0 = max(scored, key=lambda t: (t[1], -t[0]))
    k = np.round((P - c0) / T)
    on = np.abs(P - c0 - k * T) <= SPIKE_TOL_PX
    if on.sum() >= 2 and len(np.unique(k[on])) >= 2:
        T, c0 = np.polyfit(k[on], P[on], 1)
    c_first = float(c0 - np.floor(c0 / T) * T)
    resid = P[on] - (c0 + k[on] * T)
    return {"spikes": peaks, "spike_z": [float(z[c]) for c in peaks], "found": True, "T_px": float(T),
            "c_first": c_first, "n_on": int(on.sum()), "n_off": int((~on).sum()),
            "off_cols": P[~on].tolist(), "rms_px": float(np.sqrt(np.mean(resid ** 2)))}


def staircase(x: np.ndarray, w: np.ndarray, seams: list[float], mask_px: int) -> Rec:
    c = np.arange(len(x))
    ok = (w > 0) & np.isfinite(x)
    for s in seams:
        ok &= np.abs(c - s) > mask_px
    idx = np.flatnonzero(ok)
    cols = [np.ones(len(idx)), idx.astype(float)] + [(idx > s).astype(float) for s in seams]
    M = np.column_stack(cols)
    sol, *_ = np.linalg.lstsq(M, x[idx], rcond=None)
    res = x[idx] - M @ sol
    return {"slope_px_per_px": float(sol[1]), "jumps_px": sol[2:].tolist(), "rms_px": float(res.std())}


def detect(scan: Path, label: str, cell_dots: str, dpi_arg: float | None, meta: Rec) -> Rec:
    t0 = time.time()
    img, dpi = open_capture(scan, dpi_arg)
    px_mm = dpi / MM_PER_IN
    sub = dpi / PRINT_DPI
    rows_pb = max(4, int(round(BLOCK_MM * px_mm)))
    E = edge_profiles(img, rows_pb)
    del img
    t_load = time.time() - t0
    snr_by_k = {}
    if cell_dots == "auto":
        for k in CELL_CANDIDATES:
            snr_by_k[k] = peak(E, 1.0 / (k * sub))[1]
        good = [k for k in CELL_CANDIDATES if snr_by_k[k] >= AUTO_SNR]
        k_cell = max(good) if good else max(snr_by_k, key=snr_by_k.get)
    else:
        k_cell = int(cell_dots)
    f, snr = peak(E, 1.0 / (k_cell * sub))
    pitch = 1.0 / f
    ref_px = int(round(REF_MM * px_mm))
    n_coarse = int(round(WINDOW_MM * px_mm))
    chans = "K" if E.shape[0] == 1 else "RGB"
    S = [coherent(E[k], f, pitch, ref_px) for k in range(E.shape[0])]
    zs = spike_profile(E, px_mm)
    del E
    pc = profiles(S, f, n_coarse, ref_px)
    xc, wc = pc["x"], pc["w"]
    gap, length = int(round(STEP_GAP_MM * px_mm)) + n_coarse // 2, int(round(STEP_LEN_MM * px_mm))
    fit_gap, fit_len = int(round(FIT_GAP_MM * px_mm)) + n_coarse // 2, int(round(FIT_LEN_MM * px_mm))
    step_fold = fold_score(step_stat(xc, wc, gap, length), px_mm, LATTICE_BIN_MM * px_mm)
    lat = spike_lattice(zs, np.append(wc > 0, False), px_mm)
    T, c_first = (lat["T_px"], lat["c_first"]) if lat["found"] else (step_fold["T_px"], step_fold["c0"] % step_fold["T_px"])
    seams = []
    for k in range(int((len(xc) - c_first) / T) + 1):
        cp = c_first + k * T
        j = int(round(cp))
        w0, w1 = max(0, j - SPIKE_TOL_PX), min(len(zs), j + SPIKE_TOL_PX + 1)
        jj = w0 + int(np.argmax(zs[w0:w1]))
        z_run = zs[max(0, jj - 3):jj + 4]
        seams.append({"k": k, "col_pred": float(cp), "col": int(jj), "mm": float((jj + 1) / px_mm),
                      "spike_z": float(zs[jj]), "spike_width_px": int((z_run >= zs[jj] / 2).sum()),
                      "J_px": line_jump(xc, wc, jj + 0.5, fit_gap, fit_len)})
    keep = [q for q in seams if np.isfinite(q["J_px"])]
    branch_ref = float("nan")
    xch = pc["x_ch"]
    if keep:
        cols = [q["col"] + 0.5 for q in keep]
        xc, branch_ref = rebranch(xc, cols, [q["J_px"] for q in keep], pitch)
        xch = [rebranch(x, cols, [line_jump(x, wc, c, fit_gap, fit_len) for c in cols], pitch)[0] for x in xch]
        xc, xch = detrend(xc, wc), [detrend(x, wc) for x in xch]
    for q in seams:
        q["J_px"] = line_jump(xc, wc, q["col"] + 0.5, fit_gap, fit_len)
        q["J_dots"] = q["J_px"] / sub
        q["J_ch_dots"] = {chans[i]: line_jump(x, wc, q["col"] + 0.5, fit_gap, fit_len) / sub for i, x in enumerate(xch)}
    strong = [q for q in seams if q["spike_z"] >= SPIKE_Z and np.isfinite(q["J_px"])]
    found = bool(lat["found"] and lat["n_on"] >= LATTICE_MIN_SEAMS)
    st = staircase(xc, wc, [q["col"] + 0.5 for q in strong], fit_gap) if strong else {}
    Js = np.array([q["J_px"] for q in strong])
    fb = int(round(FOLD_BIN_MM * px_mm))
    kk = (np.mod(np.arange(len(xc)) - c_first - 0.5, T) // fb).astype(int)
    okf = (wc > 0) & np.isfinite(xc)
    fold_prof = [[float(b * fb / px_mm), float(np.median(xc[okf & (kk == b)]))] for b in range(int(T // fb) + 1)
                 if (okf & (kk == b)).sum() > 3]
    valid_cols = np.flatnonzero(wc > 0)
    return {"label": label, "scan": str(scan), **meta, "dpi": dpi, "mode": "grey" if chans == "K" else "rgb",
            "cols": int(len(xc) + 1), "rows_per_block": rows_pb, "cell_dots": k_cell, "auto_snr": snr_by_k,
            "pitch_px": pitch, "pitch_scale_pct": 100.0 * (pitch / (k_cell * sub) - 1), "pitch_snr": snr,
            "trend_pct": 100.0 * pc["trend"], "valid_cols": int(len(valid_cols)),
            "valid_mm": [float(valid_cols.min() / px_mm), float(valid_cols.max() / px_mm)], "spike_lattice": lat,
            "step_fold": step_fold, "branch_ref_px": branch_ref,
            "branch_margin_px": pitch / 2 - abs(branch_ref) if np.isfinite(branch_ref) else None,
            "lattice_found": found, "period_px": T, "period_mm": T / px_mm, "phase_col": c_first,
            "phase_mm": (c_first + 1) / px_mm, "lattice_cols": [c_first + 0.5 + k * T for k in range(int((len(xc) - c_first) / T) + 1)],
            "n_seams_strong": len(strong), "n_lattice": len(seams),
            "jump_px_median": float(np.median(Js)) if len(Js) else float("nan"),
            "jump_px_iqr": np.percentile(Js, [25, 75]).tolist() if len(Js) else [],
            "jump_dots_median": float(np.median(Js) / sub) if len(Js) else float("nan"),
            "jump_ch_dots_median": {q: float(np.nanmedian([z["J_ch_dots"][q] for z in strong])) for q in chans} if strong else {},
            "spike_width_px_median": float(np.median([q["spike_width_px"] for q in strong])) if strong else float("nan"),
            "staircase": st, "slope_pct": 100 * st.get("slope_px_per_px", float("nan")),
            "jump_rate_pct": 100 * float(np.median(Js)) / T if len(Js) else float("nan"),
            "fold_profile_mm_px": fold_prof, "seams": seams, "seconds_load": t_load, "seconds": time.time() - t0}


def manifest_row(published: str) -> Rec:
    with open(ARCHIVE / "MANIFEST.tsv") as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    rows = csv.DictReader(lines, delimiter="\t")
    for r in rows:
        if r["published_path"] == published:
            return r
    raise SystemExit(f"{published}: not in MANIFEST.tsv")


def rebuild(published: str, tmp: Path) -> Path:
    """The capture's raw TIFF under tmp (the archive's unpack.sh), sha256 checked against sha256_raw."""
    r = manifest_row(published)
    tmp.mkdir(parents=True, exist_ok=True)
    out = tmp / Path(published).name.removesuffix(".jxl")
    hdr = ARCHIVE / "headers" / (published.removesuffix(".jxl").replace("/", "__") + ".tiffhdr")
    subprocess.run(["sh", str(ARCHIVE / "tools" / "unpack.sh"), str(ARCHIVE / published), str(hdr), r["raw_bytes"],
                    str(out)], check=True)
    h = hashlib.sha256()
    with open(out, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 24), b""):
            h.update(chunk)
    if h.hexdigest() != r["sha256_raw"]:
        out.unlink()
        raise SystemExit(f"{published}: rebuilt sha256 {h.hexdigest()} != {r['sha256_raw']}")
    return out


def jsonable(o: Any) -> Any:
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def summary_line(r: Rec) -> str:
    lat = r["spike_lattice"]
    return (f"{r['label']}: {r['dpi']:.0f} {r['mode']} c{r['cell_dots']} pitch {r['pitch_px']:.4f} px "
            f"({r['pitch_scale_pct']:+.3f} %, trend {r['trend_pct']:+.3f} %); spikes {len(lat['spikes'])} "
            f"(on lattice {lat.get('n_on')}, off {lat.get('off_cols')}); found {r['lattice_found']}; "
            f"T {r['period_px']:.2f} px = {r['period_mm']:.3f} mm, first seam col {r['phase_col']:.1f} "
            f"({r['phase_mm']:.3f} mm); {r['n_seams_strong']}/{r['n_lattice']} seams; J {r['jump_px_median']:.2f} px = "
            f"{r['jump_dots_median']:.2f} dots {r['jump_ch_dots_median']} (branch margin {r['branch_margin_px']}); "
            f"spike width {r['spike_width_px_median']} px; slope {r['slope_pct']:.4f} % vs J/T {r['jump_rate_pct']:.4f} %; "
            f"step fold T {r['step_fold']['T_px'] / r['dpi'] * MM_PER_IN:.2f} mm z {r['step_fold']['z']:.1f}; {r['seconds']:.0f} s")


TABLE_KEYS = ("label", "capture", "date", "dpi", "mode", "orientation", "cell_dots", "lattice_found", "period_px",
              "period_mm", "first_seam_col", "first_seam_mm", "seam_mm", "n_seams_strong", "n_lattice", "spike_z_min",
              "spike_width_px", "jump_px_median", "jump_dots_median", "jump_dots_per_seam", "jump_R_dots", "jump_G_dots",
              "jump_B_dots", "branch_margin_px", "slope_pct", "jump_rate_pct", "off_lattice_spike_cols",
              "lattice_rms_px", "pitch_scale_pct", "valid_mm", "notes")


def table(out: Path) -> None:
    recs = [json.loads(p.read_text()) for p in sorted(out.glob("*.json")) if p.name != "seams.json"
            and not p.name.startswith("cost")]
    rows = []
    for r in recs:
        ch = r.get("jump_ch_dots_median") or {}
        lat = r["spike_lattice"]
        strong = [q for q in r["seams"] if q["spike_z"] >= SPIKE_Z]
        rows.append({"label": r["label"], "capture": r.get("capture") or r["scan"], "date": r.get("date"), "dpi": r["dpi"],
                     "mode": r["mode"], "orientation": r.get("orientation"), "cell_dots": r["cell_dots"],
                     "lattice_found": r["lattice_found"], "period_px": r["period_px"], "period_mm": r["period_mm"],
                     "first_seam_col": f"{r['phase_col']:.0f}|{r['phase_col'] + 1:.0f}", "first_seam_mm": r["phase_mm"],
                     "seam_mm": " ".join(f"{q['mm']:.2f}" for q in strong), "n_seams_strong": r["n_seams_strong"],
                     "n_lattice": r["n_lattice"], "spike_z_min": min((q["spike_z"] for q in strong), default=None),
                     "spike_width_px": r["spike_width_px_median"], "jump_px_median": r["jump_px_median"],
                     "jump_dots_median": r["jump_dots_median"],
                     "jump_dots_per_seam": " ".join(f"{q['J_dots']:+.2f}" if q["J_dots"] is not None else "nan" for q in strong),
                     "jump_R_dots": ch.get("R", ch.get("K")), "jump_G_dots": ch.get("G"), "jump_B_dots": ch.get("B"),
                     "branch_margin_px": r["branch_margin_px"], "slope_pct": r["slope_pct"],
                     "jump_rate_pct": r["jump_rate_pct"], "off_lattice_spike_cols": " ".join(f"{c:.0f}" for c in lat.get("off_cols", [])),
                     "lattice_rms_px": lat.get("rms_px"), "pitch_scale_pct": r["pitch_scale_pct"],
                     "valid_mm": " ".join(f"{v:.1f}" for v in r["valid_mm"]), "notes": r.get("notes")})
    with open(out / "seams.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(TABLE_KEYS))
        w.writeheader()
        for row in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()})
    (out / "seams.json").write_text(json.dumps(jsonable({"captures": recs}), indent=1))
    for row in rows:
        print(" | ".join(f"{row[k]:.3f}" if isinstance(row[k], float) else str(row[k]) for k in
                         ("label", "dpi", "mode", "cell_dots", "lattice_found", "period_mm", "first_seam_col",
                          "first_seam_mm", "n_seams_strong", "n_lattice", "spike_width_px", "jump_dots_median",
                          "slope_pct")))


def cost(a: argparse.Namespace) -> None:
    from measure.cmy_probe.bands import state_classes
    from measure.e041_probe_readout import Scan, sub_px_per_dot
    from measure.e045_left_band.cells import (fine_field, paint, paint_X, prior_offsets, read_windows,
                                              refine_subwindows, sample_field)
    from measure.e045_left_band.slices import predict
    t0 = time.time()
    a.out.mkdir(parents=True, exist_ok=True)
    seam = json.loads(a.seams_json.read_text())
    seam_cols = np.array(seam["lattice_cols"])
    man, gtz = json.loads(a.manifest.read_text()), np.load(a.gt)
    fit = json.loads(a.summary.read_text())["scans"][0]
    A, white = np.asarray(fit["fit"]["affine_mm_to_colrow"]), np.asarray(fit["page_white"], float)
    scan = Scan(a.scan)
    sub = sub_px_per_dot(scan.dpi, PRINT_DPI)
    px_mm = scan.dpi / MM_PER_IN
    dot_mm = MM_PER_IN / PRINT_DPI
    rows: list[Rec] = []
    for b in [b for b in man["bands"] if not a.bands or b["name"] in a.bands.split(",")]:
        cls = state_classes(gtz[b["gt_key"]])
        x0d, y0d, cd = int(b["x_dots"]), int(b["y_dots"]), int(b["cell_dots"])
        wins1 = read_windows(scan, A, x0d, y0d, cls, cd, white, sub, a.workers)
        wins = read_windows(scan, A, x0d, y0d, cls, cd, white, sub, a.workers, prior_offsets(wins1))
        subs = refine_subwindows(scan, A, x0d, y0d, cls, cd, white, sub, wins, a.workers)
        off_win = paint(wins, cls.shape)
        arms = {"read": paint_X(wins1, cls.shape), "win": sample_field(scan, A, x0d, y0d, cd, sub, off_win),
                "finex": sample_field(scan, A, x0d, y0d, cd, sub, fine_field(off_win, subs, crossfit=True))}
        full = np.ones(cls.shape, bool)
        xs_mm = (x0d + (np.arange(cls.shape[1]) + 0.5) * cd) * dot_mm
        ys_mm = (y0d + (np.arange(cls.shape[0]) + 0.5) * cd) * dot_mm
        col_px = A[0, 0] * xs_mm[None, :] + A[0, 1] * ys_mm[:, None] + A[0, 2]
        d_px = col_px[..., None] - seam_cols[None, None, :]
        nearest = np.take_along_axis(d_px, np.argmin(np.abs(d_px), -1)[..., None], -1)[..., 0]
        d_mm = nearest / px_mm
        rec: Rec = {"band": b["name"], "cell_dots": cd}
        for arm, X in arms.items():
            err = (predict(X, cls, full) != cls)
            rec[arm] = err
        dcol = d_mm.mean(0)
        for arm in arms:
            e_col = rec[arm].mean(0) * 100.0
            for j in range(cls.shape[1]):
                rows.append({"band": b["name"], "cell_dots": cd, "arm": arm, "col": j, "x_mm": float(xs_mm[j]),
                             "d_mm": float(dcol[j]), "err_pct": float(e_col[j]), "n": int(cls.shape[0])})
        print(f"  {b['name']} c{cd}: " + " ".join(f"{arm} {100 * rec[arm].mean():.2f} %" for arm in arms)
              + f" ({time.time() - t0:.0f} s)", flush=True)
    with open(a.out / "cost_cells.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    res = {"cells": excess_profile(rows, "d_mm", "err_pct", "n"), "seam_cols": seam_cols.tolist(),
           "sheet3_csv": csv_excess(a.sheet3_dir, A, seam_cols, px_mm), "seconds": time.time() - t0}
    (a.out / "cost.json").write_text(json.dumps(jsonable(res), indent=1))
    for name, prof in [*res["cells"].items(), *[(f"{k}:{g}", v) for k, d in res["sheet3_csv"].items() for g, v in d.items()]]:
        print(f"{name:>36}: " + " ".join(f"{q['d_mm']:+.2f}:{q['excess_pp']:+.2f}" for q in prof if abs(q["d_mm"]) <= 3.0))


def excess_profile(rows: list[Rec], dkey: str, ekey: str, nkey: str | None, bin_mm: float = 0.25,
                   base_mm: float = 4.0) -> Rec:
    """Per (cell pitch, arm): error minus the band's own baseline (its columns with |d| >= base_mm within the
    same seam period), binned by signed distance to the nearest seam; n-weighted."""
    out: Rec = {}
    groups: dict[tuple[int, str], list[Rec]] = {}
    for r in rows:
        groups.setdefault((int(r["cell_dots"]), r.get("arm", "csv")), []).append(r)
    for (cd, arm), rs in groups.items():
        by_band: dict[str, list[Rec]] = {}
        for r in rs:
            by_band.setdefault(r["band"], []).append(r)
        acc: dict[int, list[float]] = {}
        for band_rows in by_band.values():
            x = np.array([r["x_mm"] for r in band_rows])
            d = np.array([r[dkey] for r in band_rows])
            e = np.array([r[ekey] for r in band_rows])
            n = np.array([r[nkey] for r in band_rows]) if nkey else np.ones(len(e))
            period = np.round((x - d) * 10) / 10
            for p in np.unique(period):
                sel = period == p
                base = np.abs(d) >= base_mm
                if (sel & base).sum() < 3:
                    continue
                b0 = np.average(e[sel & base], weights=n[sel & base])
                for di, ei, ni in zip(d[sel], e[sel], n[sel]):
                    acc.setdefault(int(np.floor(di / bin_mm)), []).extend([ei - b0, ni])
        prof = []
        for k in sorted(acc):
            v = np.array(acc[k]).reshape(-1, 2)
            prof.append({"d_mm": (k + 0.5) * bin_mm, "excess_pp": float(np.average(v[:, 0], weights=v[:, 1])),
                         "n": float(v[:, 1].sum()), "sem_pp": float(v[:, 0].std() / np.sqrt(len(v)))})
        out[f"c{cd}_{arm}"] = prof
    return out


def csv_excess(d: Path, A: np.ndarray, seam_cols: np.ndarray, px_mm: float) -> Rec:
    out: Rec = {}
    for name, key in (("subwindows", "err_finex"), ("windows", "err_read"), ("windows", "err_finex")):
        with open(d / f"{name}.csv") as fh:
            rs = list(csv.DictReader(fh))
        rows = []
        for r in rs:
            x, y = float(r["x_mm"]), float(r["y_mm"])
            col = A[0, 0] * x + A[0, 1] * y + A[0, 2]
            dd = col - seam_cols
            rows.append({"band": r["band"], "cell_dots": int(r["cell_dots"]), "arm": f"{name}_{key}", "x_mm": x,
                         "d_mm": float(dd[np.argmin(np.abs(dd))] / px_mm), "err": float(r[key])})
        out[f"{name}_{key}"] = excess_profile(rows, "d_mm", "err", None, bin_mm=0.5)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("detect", "archive"):
        p = sp.add_parser(name)
        if name == "detect":
            p.add_argument("--scan", required=True, type=Path, help="the capture TIFF (uncompressed, contiguous)")
        else:
            p.add_argument("--capture", required=True, help="published_path in the archive's MANIFEST.tsv")
            p.add_argument("--tmp", type=Path, default=Path("/tmp/e045-seams"), help="where the TIFF is rebuilt")
        p.add_argument("--label", required=True, help="output name (<out>/<label>.json)")
        p.add_argument("--out", required=True, type=Path, help="output directory")
        p.add_argument("--cell-dots", default="auto", help="printed dots per cell, or auto")
        p.add_argument("--dpi", type=float, default=None, help="scan dpi (default: the TIFF tag)")
        p.add_argument("--date", default="", help="capture date (from the record)")
        p.add_argument("--orientation", default="", help="page orientation on the platen (from the record)")
        p.add_argument("--notes", default="", help="free text carried into the table")
    p = sp.add_parser("table")
    p.add_argument("--out", required=True, type=Path, help="directory of <label>.json")
    p = sp.add_parser("cost")
    for k in ("sheet3-dir", "scan", "manifest", "gt", "summary", "seams-json", "out"):
        p.add_argument(f"--{k}", required=True, type=Path)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--bands", default="", help="comma-separated band names (default: all)")
    a = ap.parse_args()
    if a.cmd == "table":
        table(a.out)
        return
    if a.cmd == "cost":
        cost(a)
        return
    a.out.mkdir(parents=True, exist_ok=True)
    meta = {"date": a.date, "orientation": a.orientation, "notes": a.notes}
    if a.cmd == "archive":
        t0 = time.time()
        path = rebuild(a.capture, a.tmp)
        print(f"rebuilt {path} ({time.time() - t0:.0f} s), sha256 ok", flush=True)
        try:
            rec = detect(path, a.label, a.cell_dots, a.dpi, {**meta, "capture": a.capture})
        finally:
            path.unlink()
    else:
        rec = detect(a.scan, a.label, a.cell_dots, a.dpi, meta)
    (a.out / f"{a.label}.json").write_text(json.dumps(jsonable(rec), indent=1))
    print(summary_line(rec))
    for q in rec["seams"]:
        print(f"  seam k {q['k']:2d} col {q['col']:6d} ({q['mm']:7.2f} mm) spike z {q['spike_z']:6.1f} "
              f"width {q['spike_width_px']} px J {q['J_px']:+.2f} px {q['J_dots']:+.2f} dots ch "
              f"{' '.join(f'{c} {v:+.2f}' for c, v in q['J_ch_dots'].items())}")


if __name__ == "__main__":
    main()

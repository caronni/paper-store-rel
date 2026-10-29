"""The pairwise cell checkerboards of sheet 2 (CMY-PROBE-M281 §9 item 2): dot gain, edge width, plane offset
and the screen families off the pattern's own harmonics, per patch and toner.

A manifest entry {id, pair, cell_dots, construct, x_dots, y_dots, w_dots, h_dots}: cell (i, j) (row i, column
j from the patch's top-left dot) is pair[0] when (i + j) is even, else pair[1]; "W" is unpainted paper.

Per patch, the page-aligned image is sampled through the page affine at scan px pitch (sub = scan dpi / 600
samples per printed dot, sample centres at (k + 0.5) / sub dots; cubic spline), and only its interior is
read: one pattern period P = 2 cell_dots sub samples cut from every side, then a whole number of periods.
  (a) ink fraction per toner plane: the mean unmixed coverage (below) — the inked area, invariant under the
      scanner's blur (a blur moves reflectance, it does not create or destroy it) — against the nominal 0.5
      -> dot gain in % of area and in dots of equivalent edge growth e (a checkerboard of c-dot cells whose
      inked squares grow by e on every edge: area 0.5 + 2u - 2u^2 for u = e / c >= 0 (the diagonal
      neighbours' corners overlap), 0.5 (1 + 2u)^2 for u < 0).  Beside it, as records, the two threshold
      forms: the spec's first form, the fraction above Otsu's threshold on the toner's raw ink density
      (C 255 - R, M 255 - G, Y 255 - B; ink_fraction_otsu), and the fraction above half the solid's coverage
      (ink_fraction_half).  Both are biased where the white holes are small against the blur (synthetic,
      blur sigma 1.6 px, c2, +0.3 dot: planted 0.755, Otsu 0.70-0.75, half 0.82-0.84, mean coverage
      0.755-0.761), and the Otsu form mixes in a coloured partner's absorption (Y in M/Y: 0.68);
  (b) the 10-90 % transition width across the cell boundary in um per toner: the unmixed coverage folded
      on the period (P x P tile), centred on the toner's measured offset, the profile along x through the
      middle half of the cell rows (cell row 1 rolled by one cell onto row 0) and along y likewise; the
      rise and the fall measured on the 8x linearly upsampled circular profile, their mean per axis;
  (c) the offset of each toner's pattern against the manifest position, from the phase of the pattern's
      fundamentals (the diagonals k+- = (1, +-1) / P cycles per sample; an ideal checkerboard has none on
      the axes) of the unmixed coverage against the ideal pattern's on the same samples:
      dx + dy = -dphi+ P / 2 pi, dx - dy = -dphi- P / 2 pi, unique for |dx| + |dy| < cell_dots (the
      pattern repeats under a (c, c) shift); for a coloured pair the relative offset pair[1] - pair[0]
      from the phase difference directly.  The absolute offsets carry the page fit's error; the relative
      one does not;
  (d) stipples.families on each of the three ink densities with the pattern's reciprocal lattice
      ((m, n) / P for every integer m, n, (0, 0) excepted) masked +-MASK_BINS bins per axis; a family whose
      nominal frequency falls inside the mask is NaN — it coincides with the pattern and cannot be judged
      there (the 212 lpi +-45 deg yellow stipple IS the c2 checkerboard's fundamental: a 4-dot checkerboard
      has its diagonal period at 600 / (4 / sqrt 2) = 212.1 lpi).
Unmixing (unmix): the coverage of each toner of the pair from the reflectance in the toners' own channels
(C R, M G, Y B) under the Neugebauer-Demichel model — one toner linear in its coverage (the scanner's blur
is linear in reflectance), two stacked toners multiplying as transmittances; the solids are the sheet's own
bars at the registry value (readout.toner_solids), else the patch's own Otsu classes.  (a), (b) and (c) read
the coverage, so a partner toner's absorption in the channel (magenta in B, cyan in G) does not shift them.
Outputs (readout): checkerboards.csv, summary["scans"][i]["checkerboards"], checkerboards-c<cell>.png (per
pitch: per patch the RGB at 4x, each toner's density at 4x, the folded x / y profiles).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from measure.cmy_probe.stipples import _font, families, worst
from measure.e041_probe_readout import Scan, sample_rect

TONER_CHANNEL = {"C": 0, "M": 1, "Y": 2}
MASK_BINS = 3
SPLINE_ORDER = 3            # the page-aligned resampling: a bilinear one modulates the pattern's harmonics with
#                             the sample-to-pixel phase (rotation, scale) and puts sidebands ~8 bins off them
NOMINAL_FRACTION = 0.5
COVERAGE_HALF = 0.5                         # the ink fraction's level: half the solid's coverage
UPSAMPLE = 8
ZOOM = 4
ZOOM_DOTS = (40, 20)                        # the composite's crop of each patch, printed dots (w, h)


# ---------------------------------------------------------------- geometry and the ideal pattern

def toners_of(cb: dict[str, Any]) -> list[str]:
    return [t for t in cb["pair"] if t != "W"]


def patch_image(scan: Scan, A: np.ndarray, cb: dict[str, Any], dpi: float, sub: int) -> np.ndarray:
    """(h_dots sub, w_dots sub, 3) RGB sampled page-aligned at sample centres (k + 0.5) / sub dots."""
    dot_mm = 25.4 / dpi
    xs = (int(cb["x_dots"]) + (np.arange(int(cb["w_dots"]) * sub) + 0.5) / sub) * dot_mm
    ys = (int(cb["y_dots"]) + (np.arange(int(cb["h_dots"]) * sub) + 0.5) / sub) * dot_mm
    return sample_rect(scan, A, xs, ys, order=SPLINE_ORDER)


def interior(n: int, period: int) -> slice:
    """One period cut from each side, then whole periods (the slice starts on a period boundary)."""
    k = max(1, (n - 2 * period) // period)
    return slice(period, period + k * period)


def ideal_coverage(cb: dict[str, Any], toner: str, shape: tuple[int, int], sub: int) -> np.ndarray:
    """The toner's ideal 0/1 coverage on the patch samples (cell from the sample centre's dot)."""
    cd = int(cb["cell_dots"])
    iy = ((np.arange(shape[0]) + 0.5) / sub // cd).astype(np.int64)
    ix = ((np.arange(shape[1]) + 0.5) / sub // cd).astype(np.int64)
    even = ((iy[:, None] + ix[None, :]) % 2) == 0
    a, b = cb["pair"]
    return ((even & (a == toner)) | (~even & (b == toner))).astype(np.float64)


# ---------------------------------------------------------------- (a) ink fraction

def otsu(v: np.ndarray, lo: float = 0.0, hi: float = 256.0) -> float:
    """Otsu's threshold of a sample on [lo, hi) (256 bins)."""
    hist, edges = np.histogram(np.clip(v, lo, hi), bins=256, range=(lo, hi))
    p = hist.astype(np.float64) / max(hist.sum(), 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    w0 = np.cumsum(p)
    mu = np.cumsum(p * centres)
    mt = mu[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        sb = (mt * w0 - mu) ** 2 / (w0 * (1 - w0))
    sb[~np.isfinite(sb)] = 0
    return float(edges[int(np.argmax(sb)) + 1])


def edge_growth_dots(frac: float, cell_dots: int) -> float:
    """Equivalent edge growth e (dots) of a checkerboard of cell_dots cells whose inked area is frac."""
    d = frac - NOMINAL_FRACTION
    if d >= 0:
        disc = 1.0 - 2.0 * d
        return float(cell_dots * (1.0 - np.sqrt(disc)) / 2.0) if disc >= 0 else float("nan")
    return float(cell_dots * (np.sqrt(max(2.0 * frac, 0.0)) - 1.0) / 2.0)


# ---------------------------------------------------------------- unmixing

NEWTON_STEPS = 6


def unmix(img: np.ndarray, toners: list[str], paper: np.ndarray, solids: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Per toner its coverage image, from the reflectance r = value / paper in the toners' own channels under
    the Neugebauer-Demichel model: r_c = prod_t (1 - cov_t d_tc), d_tc = 1 - solid_tc / paper_c (one toner:
    linear in its coverage, as the scanner's blur is; two toners stacked: their transmittances multiply).
    Two toners: Newton's method per pixel from the linear solution."""
    ch = [TONER_CHANNEL[t] for t in toners]
    d = np.array([[1.0 - solids[t][c] / paper[c] for t in toners] for c in ch], np.float64)   # (channel, toner)
    r = np.stack([img[..., c] / paper[c] for c in ch], -1).astype(np.float64)
    if len(toners) == 1:
        return {toners[0]: (1.0 - r[..., 0]) / d[0, 0]}
    cov = (1.0 - r) @ np.linalg.inv(d).T
    for _ in range(NEWTON_STEPS):
        g = 1.0 - cov[..., None, :] * d[None, None]                # (..., channel, toner): 1 - cov_t d_tc
        f = g[..., 0] * g[..., 1] - r
        j00, j01 = -d[0, 0] * g[..., 0, 1], -d[0, 1] * g[..., 0, 0]
        j10, j11 = -d[1, 0] * g[..., 1, 1], -d[1, 1] * g[..., 1, 0]
        det = j00 * j11 - j01 * j10
        det = np.where(np.abs(det) < 1e-9, 1e-9, det)
        cov[..., 0] -= (j11 * f[..., 0] - j01 * f[..., 1]) / det
        cov[..., 1] -= (-j10 * f[..., 0] + j00 * f[..., 1]) / det
        np.clip(cov, -0.5, 1.5, out=cov)
    return {t: cov[..., k] for k, t in enumerate(toners)}


def patch_solids(img: np.ndarray, toners: list[str]) -> dict[str, np.ndarray]:
    """Fallback solids: the median RGB of the pixels above Otsu in a toner's own density and not above it in
    the other's."""
    hi = {}
    for t in toners:
        d = 255.0 - img[..., TONER_CHANNEL[t]]
        hi[t] = d > otsu(d)
    out = {}
    for t in toners:
        m = hi[t].copy()
        for u in toners:
            if u != t:
                m &= ~hi[u]
        out[t] = np.median(img[m], axis=0) if m.any() else np.median(img[hi[t]], axis=0)
    return out


# ---------------------------------------------------------------- (c) phase

def fundamentals(v: np.ndarray, period: int) -> tuple[complex, complex]:
    """DFT coefficients at (1, 1) / P and (1, -1) / P cycles per sample (sample indices from the slice start,
    which lies on a period boundary)."""
    h, w = v.shape
    ey = np.exp(-2j * np.pi * np.arange(h) / period)
    ex = np.exp(-2j * np.pi * np.arange(w) / period)
    return complex(ey @ v @ ex), complex(np.conj(ey) @ v @ ex)


def shift_from_phases(dp: float, dm: float, period: int, sub: int) -> tuple[float, float]:
    """(dx, dy) printed dots from the phase changes at k+ and k- (wrapped to (-pi, pi])."""
    wrap = lambda a: float((a + np.pi) % (2 * np.pi) - np.pi)       # noqa: E731
    sp = -wrap(dp) * period / (2 * np.pi)
    sm = -wrap(dm) * period / (2 * np.pi)
    return 0.5 * (sp + sm) / sub, 0.5 * (sp - sm) / sub


def phase_record(cov: np.ndarray, ideal: np.ndarray, period: int, sub: int) -> dict[str, Any]:
    fp, fm = fundamentals(cov, period)
    ip, im = fundamentals(ideal, period)
    dx, dy = shift_from_phases(np.angle(fp / ip), np.angle(fm / im), period, sub)
    return {"dx_dots": dx, "dy_dots": dy, "fund_ratio": float(0.5 * (abs(fp) / abs(ip) + abs(fm) / abs(im))),
            "_norm": (fp / ip, fm / im)}


# ---------------------------------------------------------------- (b) edge width

def crossing(p: np.ndarray, start: int, stop: int, level: float, rising: bool) -> float:
    """First sub-sample position in the circular walk start -> stop where p crosses level."""
    n = len(p)
    k = start
    while k != stop:
        a, b = p[k % n], p[(k + 1) % n]
        if (rising and a < level <= b) or (not rising and a > level >= b):
            return k + (level - a) / (b - a)
        k = (k + 1) % n
    return float("nan")


def transition_width(prof: np.ndarray) -> dict[str, float]:
    """10-90 % rise and fall (samples) of one circular profile over a period, on an 8x linear upsample."""
    n = len(prof)
    t = np.arange(n * UPSAMPLE) / UPSAMPLE
    p = np.interp(t, np.arange(n + 1), np.append(prof, prof[0]))
    lo, hi = float(np.percentile(p, 2)), float(np.percentile(p, 98))
    if hi - lo <= 1e-6:
        return {"rise": float("nan"), "fall": float("nan"), "lo": lo, "hi": hi}
    l10, l90 = lo + 0.1 * (hi - lo), lo + 0.9 * (hi - lo)
    imin, imax = int(np.argmin(p)), int(np.argmax(p))
    m = len(p)
    r10, r90 = crossing(p, imin, imax, l10, True), crossing(p, imin, imax, l90, True)
    f90, f10 = crossing(p, imax, imin, l90, False), crossing(p, imax, imin, l10, False)
    rise = ((r90 - r10) % m) / UPSAMPLE if np.isfinite(r10) and np.isfinite(r90) else float("nan")
    fall = ((f10 - f90) % m) / UPSAMPLE if np.isfinite(f10) and np.isfinite(f90) else float("nan")
    return {"rise": rise, "fall": fall, "lo": lo, "hi": hi}


def folded_profiles(cov: np.ndarray, period: int, cell_px: int, dx_px: float, dy_px: float) -> tuple[np.ndarray, np.ndarray]:
    """(x profile, y profile) over one period of the folded coverage, centred on the toner's offset; the
    toner's ideal arrangement of cell row 0 (and column 0) in both."""
    h, w = cov.shape
    tile = cov.reshape(h // period, period, w // period, period).mean(axis=(0, 2))
    tile = np.roll(tile, (-int(round(dy_px)), -int(round(dx_px))), axis=(0, 1))
    q0, q1 = cell_px // 4, max(cell_px // 4 + 1, (3 * cell_px) // 4)
    row0 = tile[q0:q1].mean(0)
    row1 = np.roll(tile[cell_px + q0:cell_px + q1].mean(0), -cell_px)
    col0 = tile[:, q0:q1].mean(1)
    col1 = np.roll(tile[:, cell_px + q0:cell_px + q1].mean(1), -cell_px)
    return 0.5 * (row0 + row1), 0.5 * (col0 + col1)


# ---------------------------------------------------------------- (d) the masked families

def lattice_exclude(shape: tuple[int, int], period: int, bins: int = MASK_BINS,
                    rot_deg: float = 0.0) -> np.ndarray:
    """fftshifted boolean mask: +-bins per axis around every (m, n) / P cycles per sample but (0, 0).  With
    `rot_deg` (a scan-aligned crop of a page turned by that angle: the bands), the boxes are laid at the
    harmonics turned by +rot and by -rot as well as unturned — on a 17,000 px wide band crop 0.16 deg moves
    the 200 lpi line 4 bins along x, past a 3-bin box (sheet 2's second run)."""
    h, w = shape
    mask = np.zeros(shape, bool)
    thetas = {0.0, float(rot_deg), -float(rot_deg)}
    for m in range(-(period // 2), period // 2 + 1):
        for n in range(-(period // 2), period // 2 + 1):
            if m == 0 and n == 0:
                continue
            fy, fx = m / period, n / period
            for th in thetas:
                c, s = np.cos(np.radians(th)), np.sin(np.radians(th))
                iy = h // 2 + int(round((fy * c + fx * s) * h))
                ix = w // 2 + int(round((fx * c - fy * s) * w))
                mask[max(0, iy - bins):min(h, iy + bins + 1), max(0, ix - bins):min(w, ix + bins + 1)] = True
    return mask


def off_pattern(core: np.ndarray, period: int) -> np.ndarray:
    """The patch less its period-folded mean (per channel, the tile repeated): every exactly periodic
    component — the pattern and its harmonics, with their window leakage — removed before the spectrum; the
    tile's mean level kept so the densities stay on their scale."""
    h, w, _ = core.shape
    tile = core.reshape(h // period, period, w // period, period, 3).mean(axis=(0, 2))
    rep = np.tile(tile, (h // period, w // period, 1))
    return core - rep + tile.reshape(-1, 3).mean(0)


# ---------------------------------------------------------------- one patch

def read_checkerboard(scan: Scan, A: np.ndarray, cb: dict[str, Any], dpi: float, sub: int, paper: np.ndarray,
                      solids: dict[str, np.ndarray]) -> tuple[dict[str, Any], dict[str, Any]]:
    """(record, plot data) of one checkerboard."""
    cd = int(cb["cell_dots"])
    period, cell_px = 2 * cd * sub, cd * sub
    img = patch_image(scan, A, cb, dpi, sub)
    sy, sx = interior(img.shape[0], period), interior(img.shape[1], period)
    core = img[sy, sx]
    toners = toners_of(cb)
    sol = {t: solids[t] for t in toners if t in solids}
    if len(sol) < len(toners):
        sol = {**patch_solids(core, toners), **sol}
    cov = unmix(core, toners, paper, sol)
    um_per_px = 25400.0 / scan.dpi
    rec: dict[str, Any] = {"id": cb["id"], "pair": "/".join(cb["pair"]), "cell_dots": cd,
                           "construct": cb.get("construct"), "x_dots": int(cb["x_dots"]), "y_dots": int(cb["y_dots"]),
                           "mean_rgb": core.reshape(-1, 3).mean(0).tolist(), "toners": {}}
    plots: dict[str, Any] = {"id": cb["id"], "pair": cb["pair"], "img": img, "toners": {}}
    norms = {}
    for t in toners:
        dens = 255.0 - core[..., TONER_CHANNEL[t]]
        thr_raw = otsu(dens)
        frac_raw = float((dens > thr_raw).mean())
        frac = float(cov[t].mean())
        frac_half = float((cov[t] > COVERAGE_HALF).mean())
        ideal = ideal_coverage(cb, t, img.shape[:2], sub)[sy, sx]
        ph = phase_record(cov[t], ideal, period, sub)
        norms[t] = ph.pop("_norm")
        px_, py_ = folded_profiles(cov[t], period, cell_px, ph["dx_dots"] * sub, ph["dy_dots"] * sub)
        wx, wy = transition_width(px_), transition_width(py_)
        widths = [v for v in (wx["rise"], wx["fall"], wy["rise"], wy["fall"]) if np.isfinite(v)]
        rec["toners"][t] = {
            "ink_fraction": frac, "ink_fraction_half": frac_half, "otsu_threshold": thr_raw,
            "ink_fraction_otsu": frac_raw, "gain_area_pct": 100.0 * (frac - NOMINAL_FRACTION),
            "edge_growth_dots": edge_growth_dots(frac, cd),
            "edge_x_um": um_per_px * float(np.nanmean([wx["rise"], wx["fall"]])),
            "edge_y_um": um_per_px * float(np.nanmean([wy["rise"], wy["fall"]])),
            "edge_um": um_per_px * float(np.mean(widths)) if widths else float("nan"),
            "edge_rise_fall_x_px": [wx["rise"], wx["fall"]], "edge_rise_fall_y_px": [wy["rise"], wy["fall"]],
            **ph, "solid_rgb": [float(v) for v in sol[t]]}
        plots["toners"][t] = {"dens": 255.0 - img[..., TONER_CHANNEL[t]], "px": px_, "py": py_}
    if len(toners) == 2:
        t0, t1 = toners
        rel = shift_from_phases(np.angle(norms[t1][0] / norms[t0][0]), np.angle(norms[t1][1] / norms[t0][1]),
                                period, sub)
        rec["rel_dx_dots"], rec["rel_dy_dots"] = rel
        rec["rel_abs_dots"] = float(np.hypot(*rel))
    else:
        rec["rel_dx_dots"] = rec["rel_dy_dots"] = rec["rel_abs_dots"] = float("nan")
    fam = families(off_pattern(core, period), dpi=scan.dpi, exclude=lattice_exclude(core.shape[:2], period))
    rec["families"] = fam
    rec["worst_channel"], rec["worst_family"], rec["worst_ratio"] = worst(fam)
    return rec, plots


def read_checkerboards(scan: Scan, A: np.ndarray, entries: list[dict[str, Any]], dpi: float, sub: int,
                       paper: np.ndarray, solids: dict[str, np.ndarray], png_dir: Path | None) -> list[dict[str, Any]]:
    """Every checkerboard; one composite PNG per pitch in png_dir."""
    recs, plots = [], []
    for cb in entries:
        r, p = read_checkerboard(scan, A, cb, dpi, sub, paper, solids)
        recs.append(r)
        plots.append(p)
        print(f"  checkerboard {cb['id']} {r['pair']} c{r['cell_dots']}: " + "  ".join(
            f"{t} frac {v['ink_fraction']:.3f} edge {v['edge_um']:.0f} um off ({v['dx_dots']:+.2f}, {v['dy_dots']:+.2f})"
            for t, v in r["toners"].items()) + (f"  rel ({r['rel_dx_dots']:+.2f}, {r['rel_dy_dots']:+.2f})"
                                                if np.isfinite(r["rel_abs_dots"]) else ""))
    if png_dir is not None:
        for cd in sorted({r["cell_dots"] for r in recs}):
            sel = [(r, p) for r, p in zip(recs, plots) if r["cell_dots"] == cd]
            composite(sel, sub, png_dir / f"checkerboards-c{cd}.png")
    return recs


# ---------------------------------------------------------------- composite PNG

def _stretch(a: np.ndarray) -> np.ndarray:
    lo, hi = float(np.percentile(a, 1)), float(np.percentile(a, 99))
    return (np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1) * 255).astype(np.uint8)


def _plot(prof_x: np.ndarray, prof_y: np.ndarray, w: int, h: int, title: str) -> Image.Image:
    """The folded x (blue) and y (red) profiles over one period, PIL lines."""
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], outline="grey")
    allv = np.concatenate([prof_x, prof_y])
    lo, hi = float(allv.min()), float(allv.max())
    span = max(hi - lo, 1e-6)
    for prof, col in ((prof_x, "blue"), (prof_y, "red")):
        n = len(prof)
        pts = [(8 + (w - 16) * k / max(n - 1, 1), h - 24 - (h - 48) * (float(v) - lo) / span) for k, v in enumerate(prof)]
        d.line(pts, fill=col, width=2)
    d.text((8, 4), title, fill="black", font=_font(14))
    d.text((8, h - 20), "x blue, y red; one period", fill="grey", font=_font(12))
    return im


def composite(sel: list[tuple[dict[str, Any], dict[str, Any]]], sub: int, out: Path) -> None:
    zw, zh = ZOOM_DOTS[0] * sub, ZOOM_DOTS[1] * sub
    cw, ch = zw * ZOOM, zh * ZOOM
    pw = 360
    font = _font(16)
    W = 15 + 3 * (cw + 12) + 2 * (pw + 12)
    sheet = Image.new("RGB", (W, len(sel) * (ch + 40) + 20), "white")
    d = ImageDraw.Draw(sheet)
    y = 10
    for r, p in sel:
        img = p["img"]
        x = 15
        rgb = np.clip(img[:zh, :zw], 0, 255).astype(np.uint8)
        sheet.paste(Image.fromarray(rgb).resize((cw, ch), Image.NEAREST), (x, y + 22))
        d.text((x, y), f"{r['id']} {r['pair']} c{r['cell_dots']} {r.get('construct') or ''} — RGB {ZOOM}x", fill="black",
               font=font)
        x += cw + 12
        for t in toners_of(p):
            dens = p["toners"][t]["dens"][:zh, :zw]
            sheet.paste(Image.fromarray(_stretch(dens)).resize((cw, ch), Image.NEAREST).convert("RGB"), (x, y + 22))
            v = r["toners"][t]
            d.text((x, y), f"{t} density; frac {v['ink_fraction']:.3f} ({v['gain_area_pct']:+.1f} %), edge "
                           f"{v['edge_um']:.0f} um", fill="black", font=font)
            x += cw + 12
        if len(toners_of(p)) == 1:
            x += cw + 12
        for t in toners_of(p):
            q = p["toners"][t]
            v = r["toners"][t]
            sheet.paste(_plot(q["px"], q["py"], pw, ch, f"{t} folded coverage; off ({v['dx_dots']:+.2f}, "
                                                         f"{v['dy_dots']:+.2f}) dots"), (x, y + 22))
            x += pw + 12
        y += ch + 40
    sheet.crop((0, 0, W, y)).save(out)

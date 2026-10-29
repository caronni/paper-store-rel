"""e043 — the stipple analysis: whitened whole-patch spectra and the engine's screen families.

The lattice score of bars.py (e041's method: 1 mm windows, three lattices, the toner's own or the dark
channels) missed what the owner's eye saw on the e043 sheet: a foreign toner's screen lives in a channel
that is not the bar's own, the engine lays more lattices than e041's three, and 1 mm windows have too
little frequency resolution for a weak stipple.  This module reads each bar (or band) WHOLE: per ink
density (C = 255-R, M = 255-G, Y = 255-B) the 2-D power spectrum, whitened by its own radial median, and
the peak ratio at each known screen family — e041's 165 lpi +-14 deg, 188 lpi +-71/+-19 deg, 212 lpi
+-45 deg, and the two found on e043: dark dots at 160 lpi +-42 deg and a vertical line screen at 196 lpi.
A ratio near 10-25 is noise (the white bars); the stipples read 50-1500.
    PYTHONPATH=src:. env/bin/python -m measure.cmy_probe.stipples --scan <tiff> --manifest <json> \
        --out <dir> [--sheet 0,200,255 240,0,192 ...]
Outputs: stipples.csv (bar, channel, family -> ratio; mean RGB), bands_stipples.csv (the same per band),
the ladder tables on stdout, and with --sheet the decomposition and isolated-stipple PNGs for those values.
"""
from __future__ import annotations

import argparse
import csv
import functools
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

from measure.e041_probe_readout import Scan, fit_page

DOT_MM = 25.4 / 600
DPI = 2400.0
#: screen families (lpi, angles in degrees); the first three are e041's, the last two e043's
FAMILIES: dict[str, tuple[float, tuple[float, ...]]] = {
    "Y213@45": (213.0, (45.0, -45.0)),
    "165@14": (165.0, (14.2, -14.2)),
    "188@71/19": (188.0, (71.0, -71.0, 19.0, -19.0)),
    "dots160@42": (160.0, (42.0, -42.0)),
    "lines196@90": (196.0, (90.0,)),
}
CHANNELS = ("C", "M", "Y")          # ink densities 255 - (R, G, B)


def crop(img: np.ndarray, A: np.ndarray, b: dict[str, Any], inset_x: int = 16, inset_y: int = 4) -> np.ndarray:
    """The rectangle's interior as a scan-axis-aligned crop (corners through the page affine, sorted, so a
    page read turned 180 deg crops too; the spectrum's power is unchanged by that turn)."""
    xa, ya = (b["x_dots"] + inset_x) * DOT_MM, (b["y_dots"] + inset_y) * DOT_MM
    xb, yb = (b["x_dots"] + b["w_dots"] - inset_x) * DOT_MM, (b["y_dots"] + b["h_dots"] - inset_y) * DOT_MM
    c0, r0 = A @ np.array([xa, ya, 1.0])
    c1, r1 = A @ np.array([xb, yb, 1.0])
    ra, rb = sorted((int(round(r0)), int(round(r1))))
    ca, cb = sorted((int(round(c0)), int(round(c1))))
    return img[ra:rb, ca:cb].astype(np.float64)


N_RADIAL_BINS = 64


@functools.lru_cache(maxsize=2)
def _grid(h: int, w: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(radius cycles/px, angle deg, radial bin) of an fftshifted h x w spectrum (cached: every channel of
    a patch shares it)."""
    fy = np.fft.fftshift(np.fft.fftfreq(h))[:, None]
    fx = np.fft.fftshift(np.fft.fftfreq(w))[None, :]
    R, ang = np.hypot(fy, fx), np.degrees(np.arctan2(fy, fx))
    idx = np.clip(np.digitize(R, np.linspace(0, 0.5, N_RADIAL_BINS + 1)) - 1, 0, N_RADIAL_BINS - 1).astype(np.int8)
    for arr in (R, ang, idx):
        arr.flags.writeable = False
    return R, ang, idx


def whitened(ch: np.ndarray, exclude: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Power spectrum over its radial median (64 bins); returns (ratio, radius cycles/px, angle deg).
    `exclude` (fftshifted, the spectrum's shape) leaves those bins out of the medians (a known pattern's
    own harmonics)."""
    h, w = ch.shape
    p = (ch - ch.mean()) * np.outer(np.hanning(h), np.hanning(w))
    P = np.abs(np.fft.fftshift(np.fft.fft2(p))) ** 2
    R, ang, idx = _grid(h, w)
    med = np.ones(N_RADIAL_BINS)
    for k in range(N_RADIAL_BINS):
        m = idx == k
        if exclude is not None:
            m &= ~exclude
        if m.any():
            med[k] = np.median(P[m]) + 1e-12
    return P / med[idx], R, ang


def _angle_dist(ang: np.ndarray, dg: float) -> np.ndarray:
    return np.minimum(np.abs(((ang - dg) + 180) % 360 - 180), np.abs(((ang - dg + 180) + 180) % 360 - 180))


def _sector_boxes(f0: float, dg: float, rel: float, dang: float, h: int, w: int) -> list[tuple[slice, slice]]:
    """Index boxes of the fftshifted spectrum covering the annular sector |r - f0| < rel f0, angle within
    dang of dg or dg + 180 (the search region; the exact conditions are evaluated inside)."""
    boxes = []
    for flip in (0.0, 180.0):
        a = np.radians(np.linspace(dg + flip - dang, dg + flip + dang, 25))
        r = np.array([f0 * (1 - rel), f0 * (1 + rel)])[:, None]
        fy, fx = (r * np.sin(a)).ravel(), (r * np.cos(a)).ravel()
        y0 = max(0, int(np.floor(fy.min() * h)) + h // 2 - 2)
        y1 = min(h, int(np.ceil(fy.max() * h)) + h // 2 + 3)
        x0 = max(0, int(np.floor(fx.min() * w)) + w // 2 - 2)
        x1 = min(w, int(np.ceil(fx.max() * w)) + w // 2 + 3)
        if y1 > y0 and x1 > x0:
            boxes.append((slice(y0, y1), slice(x0, x1)))
    return boxes


def peak_at(Wp: np.ndarray, R: np.ndarray, ang: np.ndarray, lpi: float, degs: tuple[float, ...],
            rel: float = 0.05, dang: float = 6.0, dpi: float = DPI, exclude: np.ndarray | None = None) -> float:
    """The largest whitened ratio on the family's ring (+-rel) within +-dang of its angles; bins in
    `exclude` are not searched; NaN when every angle's nominal bin is excluded (the family coincides
    with the excluded pattern and cannot be judged here)."""
    f0 = lpi / dpi
    best, judged = 0.0, False
    h, w = Wp.shape
    for dg in degs:
        if exclude is not None:
            iy = h // 2 + int(round(f0 * np.sin(np.radians(dg)) * h))
            ix = w // 2 + int(round(f0 * np.cos(np.radians(dg)) * w))
            if 0 <= iy < h and 0 <= ix < w and exclude[iy, ix]:
                continue
        judged = True
        for sy, sx in _sector_boxes(f0, dg, rel, dang, h, w):
            m = (np.abs(R[sy, sx] - f0) < rel * f0) & (_angle_dist(ang[sy, sx], dg) < dang)
            if exclude is not None:
                m &= ~exclude[sy, sx]
            if m.any():
                best = max(best, float(Wp[sy, sx][m].max()))
    return best if judged else float("nan")


def families(patch: np.ndarray, dpi: float = DPI, exclude: np.ndarray | None = None) -> dict[str, dict[str, float]]:
    """{channel: {family: ratio}} for one RGB patch (scan px at `dpi`); `exclude` as in peak_at."""
    out: dict[str, dict[str, float]] = {}
    for k, nm in enumerate(CHANNELS):
        Wp, R, ang = whitened(255.0 - patch[..., k], exclude)
        out[nm] = {f: peak_at(Wp, R, ang, *FAMILIES[f], dpi=dpi, exclude=exclude) for f in FAMILIES}
    return out


LOCAL_HALF_BINS = 8          # local whitening: the median over +-8 bins around each searched bin


def power(ch: np.ndarray) -> np.ndarray:
    """The Hann-windowed, mean-removed, fftshifted power spectrum (whitened's numerator)."""
    h, w = ch.shape
    p = (ch - ch.mean()) * np.outer(np.hanning(h), np.hanning(w))
    return np.abs(np.fft.fftshift(np.fft.fft2(p))) ** 2


def peak_local(P: np.ndarray, R: np.ndarray, ang: np.ndarray, lpi: float, degs: tuple[float, ...],
               rel: float = 0.05, dang: float = 6.0, dpi: float = DPI, half: int = LOCAL_HALF_BINS,
               exclude: np.ndarray | None = None) -> float:
    """peak_at with LOCAL whitening: each searched bin over the median of the (2 half + 1)^2 bins around it.
    For a cell field (a band), whose power is anisotropic at the families' radii (a c3 field's sinc^2
    envelope puts ~2x more power on the diagonals than on the axes at 212 lpi: the radial median reads a
    clean c3 band's Y213@45 at ~60), where the radial median is not the local level.  `exclude` (fftshifted
    bool, the cell lattice's harmonics): those bins are neither searched nor in the medians (replaced by the
    box's unexcluded median); a family whose every searched bin is excluded reads NaN — it coincides with
    the lattice (a c3 field's 200 lpi line at 0/90 deg sits inside lines196@90) and cannot be judged."""
    f0 = lpi / dpi
    best = float("nan")
    h, w = P.shape
    for dg in degs:
        for sy, sx in _sector_boxes(f0, dg, rel, dang, h, w):
            y0, y1 = max(0, sy.start - half), min(h, sy.stop + half)
            x0, x1 = max(0, sx.start - half), min(w, sx.stop + half)
            box = P[y0:y1, x0:x1]
            m = (np.abs(R[sy, sx] - f0) < rel * f0) & (_angle_dist(ang[sy, sx], dg) < dang)
            if exclude is not None:
                ex = exclude[y0:y1, x0:x1]
                if ex.any():
                    box = box.copy()
                    box[ex] = np.median(box[~ex]) if (~ex).any() else 0.0
                m &= ~exclude[sy, sx]
            med = ndimage.median_filter(box, size=2 * half + 1, mode="nearest")
            iy, ix = slice(sy.start - y0, sy.stop - y0), slice(sx.start - x0, sx.stop - x0)
            if m.any():
                v = float((P[sy, sx] / (med[iy, ix] + 1e-12))[m].max())
                best = v if not (best >= v) else best
    return best


def families_local(patch: np.ndarray, dpi: float = DPI, exclude: np.ndarray | None = None) -> dict[str, dict[str, float]]:
    """{channel: {family: ratio}} with local whitening (peak_local): the band form; `exclude` as in peak_local."""
    out: dict[str, dict[str, float]] = {}
    h, w = patch.shape[:2]
    R, ang, _ = _grid(h, w)
    for k, nm in enumerate(CHANNELS):
        P = power(255.0 - patch[..., k])
        out[nm] = {f: peak_local(P, R, ang, *FAMILIES[f], dpi=dpi, exclude=exclude) for f in FAMILIES}
    return out


def worst(fam: dict[str, dict[str, float]]) -> tuple[str, str, float]:
    """(channel, family, ratio) of the largest finite ratio over every channel and family."""
    best = ("", "", float("nan"))
    for ch, fs in fam.items():
        for f, v in fs.items():
            if np.isfinite(v) and not (best[2] >= v):
                best = (ch, f, float(v))
    return best


def bandpass(ch: np.ndarray, lpi: float, deg: float, rel: float = 0.12, half_angle: float = 12.0) -> np.ndarray:
    h, w = ch.shape
    F = np.fft.fftshift(np.fft.fft2(ch - ch.mean()))
    fy = np.fft.fftshift(np.fft.fftfreq(h))[:, None]
    fx = np.fft.fftshift(np.fft.fftfreq(w))[None, :]
    R, ang = np.hypot(fy, fx), np.degrees(np.arctan2(fy, fx))
    d = np.minimum(np.abs(((ang - deg) + 180) % 360 - 180), np.abs(((ang - deg + 180) + 180) % 360 - 180))
    mask = (np.abs(R - lpi / DPI) < rel * lpi / DPI) & (d < half_angle)
    return np.real(np.fft.ifft2(np.fft.ifftshift(F * mask)))


def _stretch(ch: np.ndarray, lo: float | None = None, hi: float | None = None) -> np.ndarray:
    lo = float(np.percentile(ch, 0.5)) if lo is None else lo
    hi = float(np.percentile(ch, 99.5)) if hi is None else hi
    return (np.clip((ch - lo) / max(hi - lo, 1e-6), 0, 1) * 255).astype(np.uint8)


def _font(size: int):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except OSError:
        return ImageFont.load_default()


def stipple_sheet(img: np.ndarray, A: np.ndarray, bars: list[dict[str, Any]], out: Path) -> None:
    """Per bar: RGB at 4x, and per ink density its zoom and the band-pass at its strongest family."""
    ZW, ZH, Z = 190, 95, 4
    CW, CH = ZW * Z, ZH * Z
    font = _font(18)
    sheet = Image.new("RGB", (7 * (CW + 12) + 30, len(bars) * (CH + 70) + 30), "white")
    d = ImageDraw.Draw(sheet)
    y = 15
    for b in bars:
        c = crop(img, A, b)
        fam = families(c)
        x = 15
        sheet.paste(Image.fromarray(c[:ZH, :ZW].astype(np.uint8)).resize((CW, CH), Image.NEAREST), (x, y + 22))
        d.text((x, y), f"{tuple(b['rgb'])} {b.get('construct', '')}  mean "
                       f"({c[..., 0].mean():.0f},{c[..., 1].mean():.0f},{c[..., 2].mean():.0f}) — RGB, 2 x 1 mm at 4x",
               fill="black", font=font)
        x += CW + 12
        for k, nm in enumerate(CHANNELS):
            dens = 255.0 - c[..., k]
            best = max(fam[nm], key=fam[nm].get)
            lpi, degs = FAMILIES[best]
            bp = bandpass(dens, lpi, degs[0])
            rms = float(bp.std())
            sheet.paste(Image.fromarray(_stretch(dens[:ZH, :ZW])).resize((CW, CH), Image.NEAREST).convert("RGB"),
                        (x, y + 22))
            d.text((x, y), f"{nm} density zoom", fill="black", font=font)
            x += CW + 12
            sheet.paste(Image.fromarray(_stretch(bp[:ZH, :ZW], -3 * rms, 3 * rms)).resize((CW, CH), Image.NEAREST)
                        .convert("RGB"), (x, y + 22))
            d.text((x, y), f"band-pass {best} (ratio {fam[nm][best]:.0f}); rms {rms:.2f} = "
                           f"{100 * rms / max(dens.mean(), 1):.1f} % of mean density {dens.mean():.0f}",
                   fill="red" if fam[nm][best] > 25 else "black", font=font)
            x += CW + 12
        y += CH + 70
    sheet.crop((0, 0, sheet.width, y)).save(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheet", nargs="*", default=(), help="r,g,b values to render on the stipple sheet")
    args = ap.parse_args()
    man = json.load(open(args.manifest))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scan = Scan(Path(args.scan))
    A, _ = fit_page(scan, {"fiducials": man["fiducials"]}, 0.3, 0.01)
    img = scan.img
    rows: list[dict[str, Any]] = []
    for b in man["bars"]:
        if not b.get("rgb") and b["kind"] not in ("white", "scrambled"):
            continue
        c = crop(img, A, b)
        fam = families(c)
        for ch in CHANNELS:
            rows.append({"id": b["id"], "kind": b["kind"], "construct": b.get("construct"),
                         "toner": b.get("toner"), "axis": b.get("axis"),
                         "r": (b.get("rgb") or ["", "", ""])[0], "g": (b.get("rgb") or ["", "", ""])[1],
                         "b": (b.get("rgb") or ["", "", ""])[2], "channel": ch,
                         "mean_R": round(float(c[..., 0].mean()), 1), "mean_G": round(float(c[..., 1].mean()), 1),
                         "mean_B": round(float(c[..., 2].mean()), 1),
                         **{f: round(v, 1) for f, v in fam[ch].items()}})
    keys = list(rows[0].keys())
    with open(out / "stipples.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    # the bands, whole
    brows: list[dict[str, Any]] = []
    for band in man["bands"]:
        c = crop(img, A, band, inset_x=24, inset_y=8)
        fam = families(c)
        for ch in CHANNELS:
            brows.append({"band": band["name"], "arm": band["arm"], "channel": ch,
                          **{f: round(v, 1) for f, v in fam[ch].items()}})
    with open(out / "bands_stipples.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(brows[0].keys()))
        w.writeheader()
        w.writerows(brows)
    print("bands (whole-band whitened ratios; a stipple that survives inside the cells shows here):")
    for r in brows:
        print(f"  {r['band']} {r['arm']:6s} {r['channel']}: " + "  ".join(f"{f} {r[f]:6.1f}" for f in FAMILIES))
    # ladder tables: per toner and axis, the family that matters, by swept value
    def ladder(toner: str, axis: str, fixed: dict[str, int]) -> list[dict[str, Any]]:
        sel = [r for r in rows if r["kind"] == "sweep" and r["toner"] == toner and r["axis"] == axis
               and all(int(r[k]) == v for k, v in fixed.items())]
        key = {"R": "r", "G": "g", "B": "b", "RG": "r"}[axis]
        return sorted(sel, key=lambda r: int(r[key]))
    print("\nladders (whitened ratio by swept value; noise 10-25):")
    for title, toner, axis, fixed, cols in (
            ("C swept G (R0 B255): yellow stipple [Y Y213@45], the cyan's own screen [C 165@14]", "C", "G", {"r": 0, "b": 255},
             (("Y", "Y213@45"), ("C", "165@14"))),
            ("M swept B (R240 G0): yellow stipple [Y Y213@45], the magenta's own screen [M 165@14]", "M", "B", {"r": 240, "g": 0},
             (("Y", "Y213@45"), ("M", "165@14"))),
            ("M swept R (G0 B192): cyan dots [C 165@14], yellow stipple [Y Y213@45]", "M", "R", {"g": 0, "b": 192},
             (("C", "165@14"), ("Y", "Y213@45"))),
            ("Y swept R=G (B0): dark dots [C dots160@42], lines [C lines196@90]", "Y", "RG", {"b": 0},
             (("C", "dots160@42"), ("C", "lines196@90")))):
        print(f"  {title}")
        key = {"R": "r", "G": "g", "B": "b", "RG": "r"}[axis]
        by_val: dict[int, dict[str, float]] = {}
        for r in ladder(toner, axis, fixed):
            by_val.setdefault(int(r[key]), {})[r["channel"]] = r
        for v in sorted(by_val):
            print("    " + f"{v:3d}: " + "  ".join(f"{ch} {fam} {by_val[v][ch][fam]:7.1f}" for ch, fam in cols))
    if args.sheet:
        want = [tuple(int(t) for t in s.split(",")) for s in args.sheet]
        chosen = []
        for rgb in want:
            cands = [b for b in man["bars"] if b.get("rgb") and tuple(b["rgb"]) == rgb]
            cands.sort(key=lambda b: (b.get("construct") != "mask-hex", b["id"]))
            if cands:
                chosen.append(cands[0])
        stipple_sheet(img, A, chosen, out / "stipples.png")
        print(f"wrote {out / 'stipples.png'}")


if __name__ == "__main__":
    main()

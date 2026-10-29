"""e044 — two printed cmy pages' PAGE FIELDS compared on one page grid (2026-10-12).  MEASUREMENT ONLY: it reads
the receiver's fact snapshots (`facts.npz`, the standing `PlaneField` per page and plane) and mints nothing.

Sheets A (c2-cmy-r0775x0700@53x37) and B (c3-cmy-r0850@35x24) were printed back to back on the M281 (pages
3412 -> 3414) and each read whole on machine 4 from two captures with --complete (§044.6, §044.7).  Their fields are
the engine's M and Y displacement against C (F_C == 0 is the gauge, R7), per tile, in printed dots along the
PAGE axes: x = the short page axis (210 mm, across the process direction), y = the long axis (297 mm, along it).
The tile matrices are centred on the page (format/layout: origin = slack // 2), so both fields are put on one
2 mm grid from the page centre and compared where BOTH have measured support (`support > 0`; the prior
interpolates everywhere else and that is not a measurement).  Three readings:

1. the fields side by side — means, rms difference, Pearson/Spearman per plane and component, and 20 mm-bin
   profiles across (x) and along (y) the page;
2. the along-page WOBBLE — a least-squares sinusoid over 20–200 mm on each field's y profile (mean over x), its
   period, amplitude and phase; the phase difference between the sheets at 70/72 mm;
3. the owner's RECONCILIATION model (2026-10-12): the two prints differ by a shift of the along-page pattern
   (the roller's phase advanced between consecutive pages) plus a constant per plane and print, optionally a
   skew in x — B's field is evaluated at y + s for s in [-40, 40] mm, the residual A - B(s) has a constant (and
   a + b·x) removed, and the rms of what is left is reported against the shift; one COMMON shift for M dy and
   Y dy with the offsets per plane is the model's test.

The figure (PIL, no matplotlib in env/) draws M dx, M dy, Y dx, Y dy as A | B | A - B, red +, blue -, grey = no
common support.

    PYTHONPATH=src:. env/bin/python -m measure.e044_cmy_truth.compare_page_fields \\
        --a scratch/e044/M4/rundir.30630/facts.npz --a-cell-dots 2 \\
        --b scratch/e044/M3/rundir.30447/facts.npz --b-cell-dots 3 \\
        --figure scratch/e044/fields-A-c2-vs-B-c3.png

Measured 2026-10-12 (the record is e044 §044.8): dx agrees across the page (rms 0.22/0.25 dots, r 0.83/0.79,
means +1.0 on both sheets); dy is a 69–75 mm wobble of 0.5–0.6 dots on both, out of phase by ~100 deg; a common
shift of -23 mm plus a constant per plane (M +0.70, Y -0.15 dots) brings dy to rms 0.33, r 0.90/0.91; the skew
term buys nothing.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.stats import pearsonr, spearmanr

from holo.receiver import data, snapshot

MM_PER_DOT = 25.4 / 600
TILE_CELLS = 64
PLANES = {1: "M", 2: "Y"}
GRID_STEP_MM = 2.0
HALF_X_MM, HALF_Y_MM = 98.0, 141.0          # a little past A4-4mm's usable half extents
PROFILE_BIN_MM = 20.0
SHIFTS_MM = np.arange(-40.0, 40.1, 1.0)
PERIODS_MM = np.arange(20.0, 200.5, 1.0)


def load(path: Path, cell_dots: int):
    fields = {f.plane: f for f in snapshot.read(path)
              if isinstance(f, data.PlaneField) and f.page == 0}
    ty, tx, _ = next(iter(fields.values())).delta_dots_xy.shape
    tile_mm = TILE_CELLS * cell_dots * MM_PER_DOT
    ys = (np.arange(ty) - (ty - 1) / 2) * tile_mm      # tile centres, mm from the page centre, long axis
    xs = (np.arange(tx) - (tx - 1) / 2) * tile_mm      # short axis
    return fields, ys, xs, tile_mm


def interp(grid: np.ndarray, ys, xs, Yq, Xq) -> np.ndarray:
    f = RegularGridInterpolator((ys, xs), np.asarray(grid, np.float64),
                                bounds_error=False, fill_value=np.nan)
    return f(np.stack([Yq.ravel(), Xq.ravel()], 1)).reshape(Yq.shape)


def profile(v, m, coord, edges):
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = m & (coord >= lo) & (coord < hi) & np.isfinite(v)
        out.append(v[sel].mean() if sel.sum() > 5 else np.nan)
    return np.array(out)


def sinusoid(y, v, period):
    basis = np.stack([np.sin(2 * np.pi * y / period), np.cos(2 * np.pi * y / period)], 1)
    coef, *_ = np.linalg.lstsq(basis, v, rcond=None)
    resid = v - basis @ coef
    return np.hypot(*coef), np.degrees(np.arctan2(coef[1], coef[0])), 1 - resid.var() / v.var()


def y_profile(field, ys, tile_mm, component):
    v = np.where(field.support > 0, field.delta_dots_xy[..., component], np.nan)
    prof = np.nanmean(v, axis=1)
    prof = np.nan_to_num(prof - np.nanmean(prof))
    return ys, prof


def residual_rms(d, x, mode):
    if mode == "raw":
        r = d
    elif mode == "offset":
        r = d - d.mean()
    else:
        basis = np.stack([np.ones_like(x), x], 1)
        coef, *_ = np.linalg.lstsq(basis, d, rcond=None)
        r = d - basis @ coef
    return float(np.sqrt((r ** 2).mean()))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", type=Path, required=True, help="facts.npz of sheet A's run")
    ap.add_argument("--a-cell-dots", type=int, required=True)
    ap.add_argument("--b", type=Path, required=True, help="facts.npz of sheet B's run")
    ap.add_argument("--b-cell-dots", type=int, required=True)
    ap.add_argument("--figure", type=Path, default=None)
    args = ap.parse_args()

    A, ysA, xsA, tA = load(args.a, args.a_cell_dots)
    B, ysB, xsB, tB = load(args.b, args.b_cell_dots)
    for name, F, t in (("A", A, tA), ("B", B, tB)):
        for p, f in sorted(F.items()):
            d, s = f.delta_dots_xy, f.support > 0
            print(f"{name} plane {p} {PLANES.get(p, 'C')}: grid {d.shape[:2]} tile {t:.3f} mm  support>0 "
                  f"{s.mean():.0%}  ordinal {f.ordinal} obs {f.n_observations} captures {f.n_captures}  "
                  f"dx {d[..., 0][s].mean():+.2f} sd {d[..., 0][s].std():.2f}  "
                  f"dy {d[..., 1][s].mean():+.2f} sd {d[..., 1][s].std():.2f}")

    gx = np.arange(-HALF_X_MM, HALF_X_MM + 0.01, GRID_STEP_MM)
    gy = np.arange(-HALF_Y_MM, HALF_Y_MM + 0.01, GRID_STEP_MM)
    X, Y = np.meshgrid(gx, gy)
    xe = np.arange(-100, 101, PROFILE_BIN_MM)
    ye = np.arange(-140, 141, PROFILE_BIN_MM)

    # 1. side by side
    print("\n1. side by side on the common measured support")
    print("plane comp |  mean A   mean B |  diff mean  rms | pearson spearman | n cells")
    maps = {}
    for p, pn in PLANES.items():
        sA = interp(A[p].support, ysA, xsA, Y, X)
        sB = interp(B[p].support, ysB, xsB, Y, X)
        m = (sA > 0) & (sB > 0)
        for c, cn in ((0, "dx"), (1, "dy")):
            a = interp(A[p].delta_dots_xy[..., c], ysA, xsA, Y, X)
            b = interp(B[p].delta_dots_xy[..., c], ysB, xsB, Y, X)
            mm = m & np.isfinite(a) & np.isfinite(b)
            a_, b_ = a[mm], b[mm]
            diff = a_ - b_
            print(f"{pn:>5} {cn}  | {a_.mean():+7.2f} {b_.mean():+7.2f} | {diff.mean():+8.2f} "
                  f"{np.sqrt((diff ** 2).mean()):5.2f} | {pearsonr(a_, b_)[0]:+6.2f} "
                  f"{spearmanr(a_, b_)[0]:+8.2f} | {mm.sum()}")
            maps[(p, c)] = (a, b, mm)
    for p, pn in PLANES.items():
        for c, cn in ((0, "dx"), (1, "dy")):
            a, b, mm = maps[(p, c)]
            print(f"\n{pn} {cn} across the page (x, {PROFILE_BIN_MM:.0f} mm bins {xe[0]:+.0f}..{xe[-1]:+.0f}):")
            for nm, v in (("A", a), ("B", b)):
                print(f"  {nm}:", " ".join(f"{q:+5.2f}" for q in profile(v, mm, X, xe)))
            print(f"{pn} {cn} along the page (y, {PROFILE_BIN_MM:.0f} mm bins {ye[0]:+.0f}..{ye[-1]:+.0f}):")
            for nm, v in (("A", a), ("B", b)):
                print(f"  {nm}:", " ".join(f"{q:+5.2f}" for q in profile(v, mm, Y, ye)))

    # 2. the along-page wobble
    print("\n2. the along-page wobble: y profile (mean over x), best sinusoid over "
          f"{PERIODS_MM[0]:.0f}-{PERIODS_MM[-1]:.0f} mm")
    for name, F, ys, t in (("A", A, ysA, tA), ("B", B, ysB, tB)):
        for p, pn in PLANES.items():
            for c, cn in ((0, "dx"), (1, "dy")):
                y, prof = y_profile(F[p], ys, t, c)
                fits = sorted(((sinusoid(y, prof, per), per) for per in PERIODS_MM),
                              key=lambda r: -r[0][2])
                (amp, phase, r2), per = fits[0]
                print(f"  {name} {pn} {cn}: profile sd {prof.std():.2f} dots; period {per:.0f} mm "
                      f"amp {amp:.2f} dots phase {phase:+.0f} deg (R2 {r2:.2f}); next {fits[1][1]:.0f}/{fits[2][1]:.0f} mm")
    for per in (70.0, 72.0):
        for p, pn in PLANES.items():
            ya, pa = y_profile(A[p], ysA, tA, 1)
            yb, pb = y_profile(B[p], ysB, tB, 1)
            aa, pha, _ = sinusoid(ya, pa, per)
            ab, phb, _ = sinusoid(yb, pb, per)
            dphi = (pha - phb + 180) % 360 - 180
            print(f"  {pn} dy at {per:.0f} mm: A amp {aa:.2f} phase {pha:+.0f}, B amp {ab:.2f} phase {phb:+.0f}; "
                  f"difference {dphi:+.0f} deg = {dphi / 360 * per:+.0f} mm")

    # 3. reconciliation: shift along y + offset (+ skew) per plane
    print("\n3. reconciliation: B evaluated at y + s; residual A - B(s) after an offset / offset + skew in x")
    def shifted(p, c, s):
        a = interp(A[p].delta_dots_xy[..., c], ysA, xsA, Y, X)
        sA = interp(A[p].support, ysA, xsA, Y, X)
        b = interp(B[p].delta_dots_xy[..., c], ysB, xsB, Y + s, X)
        sB = interp(B[p].support, ysB, xsB, Y + s, X)
        m = (sA > 0) & (sB > 0) & np.isfinite(a) & np.isfinite(b)
        return a, b, m
    for p, pn in PLANES.items():
        for c, cn in ((1, "dy"), (0, "dx")):
            rows = []
            for s in SHIFTS_MM:
                a, b, m = shifted(p, c, s)
                d, x = (a - b)[m], X[m]
                rows.append((s, residual_rms(d, x, "raw"), residual_rms(d, x, "offset"),
                             residual_rms(d, x, "skew"), np.corrcoef(a[m], b[m])[0, 1]))
            rows = np.array(rows)
            i0 = int(np.argmin(np.abs(rows[:, 0])))
            ib = int(np.argmin(rows[:, 2]))
            ik = int(np.argmin(rows[:, 3]))
            print(f"  {pn} {cn}: s=0 rms raw {rows[i0, 1]:.2f} / offset {rows[i0, 2]:.2f} / offset+skew "
                  f"{rows[i0, 3]:.2f}, r {rows[i0, 4]:+.2f};  best offset s={rows[ib, 0]:+.0f} mm rms "
                  f"{rows[ib, 2]:.2f} r {rows[ib, 4]:+.2f};  best offset+skew s={rows[ik, 0]:+.0f} mm rms {rows[ik, 3]:.2f}")
            print("     rms(offset) vs s:", " ".join(f"{s:+.0f}:{v:.2f}" for s, v in zip(rows[::5, 0], rows[::5, 2])))
    best = None
    for s in SHIFTS_MM:
        tot = n = 0
        for p in PLANES:
            a, b, m = shifted(p, 1, s)
            d, x = (a - b)[m], X[m]
            basis = np.stack([np.ones_like(x), x], 1)
            coef, *_ = np.linalg.lstsq(basis, d, rcond=None)
            tot += ((d - basis @ coef) ** 2).sum()
            n += m.sum()
        rms = float(np.sqrt(tot / n))
        if best is None or rms < best[1]:
            best = (s, rms)
    s = best[0]
    print(f"  one common shift for M dy and Y dy (offset + skew per plane): s = {s:+.0f} mm, rms {best[1]:.2f}")
    for p, pn in PLANES.items():
        a, b, m = shifted(p, 1, s)
        d, x = (a - b)[m], X[m]
        basis = np.stack([np.ones_like(x), x], 1)
        coef, *_ = np.linalg.lstsq(basis, d, rcond=None)
        print(f"     {pn}: A - B(s) = {coef[0]:+.2f} dots {coef[1] * 100:+.2f} dots per 100 mm of x; "
              f"r after the shift {np.corrcoef(a[m], b[m])[0, 1]:+.2f}")

    if args.figure is not None:
        from PIL import Image, ImageDraw

        def colours(v, lim):
            t = np.clip(v / lim, -1, 1)
            r = np.where(t > 0, 255, 255 + 255 * t)
            b = np.where(t < 0, 255, 255 - 255 * t)
            g = 255 - 255 * np.abs(t)
            rgb = np.stack([r, g, b], -1)
            rgb[~np.isfinite(v)] = 128
            return rgb.astype(np.uint8)
        scale, pad, lim = 2, 30, 3.0
        h, w = X.shape
        panels = []
        for (p, c) in [(1, 0), (1, 1), (2, 0), (2, 1)]:
            a, b, mm = maps[(p, c)]
            row = []
            for v, nm in ((a, "A"), (b, "B"), (a - b, "A - B")):
                img = Image.fromarray(colours(np.where(mm, v, np.nan)[::-1], lim))
                row.append((img.resize((w * scale, h * scale), Image.NEAREST),
                            f"{nm}  {PLANES[p]} {'dx' if c == 0 else 'dy'}  (dots, +-{lim:g})"))
            panels.append(row)
        W = 3 * (w * scale + pad) + pad
        H = 4 * (h * scale + pad) + pad + 20
        canvas = Image.new("RGB", (W, H), "white")
        draw = ImageDraw.Draw(canvas)
        draw.text((pad, 4), f"page fields {args.a.name} (A) vs {args.b.name} (B): x = short page axis "
                  "(horizontal), y = long axis (vertical); red +, blue -, grey = no common support", fill="black")
        for i, row in enumerate(panels):
            for j, (img, title) in enumerate(row):
                x0 = pad + j * (w * scale + pad)
                y0 = 20 + pad + i * (h * scale + pad)
                canvas.paste(img, (x0, y0))
                draw.text((x0, y0 - 14), title, fill="black")
        args.figure.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(args.figure)
        print(f"\nfigure: {args.figure} {canvas.size}")


if __name__ == "__main__":
    main()

"""W9 — can a better statistic separate 'oversampled' from 'destroyed'?

Historical record of the W8/W9/W10 campaign; the captures are in the
evidence archive (shas in the e031 log), joined onto --scan-root:
    env/bin/python experiments/031-xerox-altalink-discovery/w9_capture_forensics.py \\
        --scan-root <evidence>

Read-only. On a blank-paper patch of each capture, measures four things.
Verdicts recorded in docs/CHARACTERIZE-WORKPLAN.md W9:

  A. variance vs k x k block averaging      *** CONFOUNDED - DO NOT REUSE ***
  B. radial power spectrum                  ADOPT - the discriminator
  C. histogram / level occupancy + entropy  ADOPT - the quantisation gate
  D. gzip ratio of the raw bytes            REJECT - tracks dynamic range

*** SECTION A IS WRONG AND ITS OUTPUT MUST BE IGNORED. ***
On blank paper, variance vs block averaging measures paper FORMATION - real
physical structure out to millimetre scales - not sensor noise.  Its
"independent-sample pitch" line therefore does NOT measure an oversampling
factor and must not be used to derive one.  It is left in the file only so
that the wrong answer stays visible next to the right ones; delete it if
this ever becomes a shipped method.

B is the one that answers the question: the spectral knee sits at a fixed
PHYSICAL frequency (14-22 lp/mm, on e028's knife-edge MTF10 of ~17 lp/mm)
rather than at a fixed fraction of Nyquist.  Optics are fixed in lp/mm;
resampling cliffs are fixed in f/Nyquist.  The 2400-dpi capture is the
control that separates them and must be preserved.

C is clean on all four captures (contiguous levels, zero interior gaps), so
no quantisation family is present.

D looks damning (0.33-0.45) until the order-0 entropy bound is computed:
3.7 bits/px / 8 = 0.46.  It measures dynamic range, not processing.

RETRACTION (W9 second pass): section B's knee reading is
patch-unstable — six patches per capture span 15-32 lp/mm within
one sheet, and the single-patch cross-DPI agreement this file
once showed was luck.  See CHARACTERIZE-WORKPLAN W9/W10; the
flatness/knee advisory built on it was retired.
"""
import argparse
import gzip
import sys
import numpy as np
import tifffile

CAPS = [
    ("e031 xerox discovery B/W", "in/xerox-canon-cal-bw.tiff", 4800, False),
    ("e031 xerox discovery clr", "in/xerox-canon-cal-color.tiff", 4800, True),
    ("e028 m281 discovery B/W", "e028/e028-m281-20260804-bw-01-canon-4800gray.tiff", 4800, False),
    ("e032 xerox c3-cmy7 2400", "in/xerox-canon-c3-cmy7-2400dpi.tiff", 2400, True),
]
_ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
_ap.add_argument("--scan-root", required=True,
                 help="evidence dir standing for the old scratch/ root")
ROOT = _ap.parse_args().scan_root.rstrip("/") + "/"
PATCH_MM = 8.0


def blank_patch(path, dpi, color):
    """Find the blankest PATCH_MM tile in a margin band and return it."""
    a = tifffile.memmap(ROOT + path)
    px = int(PATCH_MM / 25.4 * dpi)
    best = None
    h = a.shape[0]
    for y in range(int(h * 0.15), int(h * 0.85), px * 3):
        for x in range(int(a.shape[1] * 0.90), int(a.shape[1] * 0.99) - px, px):
            t = np.asarray(a[y:y + px, x:x + px], np.float64)
            if t.shape[0] < px or t.shape[1] < px:
                continue
            g = t.mean(axis=2) if color else t
            score = g.mean() - 3.0 * g.std()
            if best is None or score > best[0]:
                best = (score, g)
    return best[1]


def report(name, g, dpi):
    print(f"\n{'='*72}\n{name}   ({dpi} dpi, patch {g.shape[0]}x{g.shape[1]} px, "
          f"mean {g.mean():.2f}, std {g.std():.3f})\n{'='*72}")

    # --- A. variance vs block averaging ---------------------------------
    print("A. variance vs k x k block averaging  (white noise -> var/k^2)")
    v1 = g.var()
    print(f"   {'k':>3} {'block µm':>9} {'variance':>10} {'var*k^2/var1':>13} "
          f"{'verdict':>22}")
    eff = None
    for k in (1, 2, 4, 8, 16, 32):
        n = (g.shape[0] // k) * k
        b = g[:n, :n].reshape(n // k, k, n // k, k).mean(axis=(1, 3))
        ratio = b.var() * k * k / v1
        # white noise keeps ratio ~1; correlated pixels keep VARIANCE up,
        # so ratio climbs with k
        verdict = ("white" if ratio < 1.6 else
                   "correlated" if ratio < 6 else "strongly correlated")
        print(f"   {k:>3} {k/dpi*25400:>9.1f} {b.var():>10.4f} "
              f"{ratio:>13.2f} {verdict:>22}")
        if eff is None and ratio >= 1.6:
            eff = k
    print(f"   -> independent-sample pitch >= {eff or 1} px "
          f"= {(eff or 1)/dpi*25400:.0f} um "
          f"=> effective {dpi/(eff or 1):.0f} dpi of real information")

    # --- B. radial power spectrum ---------------------------------------
    n = min(g.shape[0], g.shape[1], 1024)
    w = g[:n, :n] - g[:n, :n].mean()
    win = np.hanning(n)[:, None] * np.hanning(n)[None, :]
    P = np.abs(np.fft.fftshift(np.fft.fft2(w * win))) ** 2
    cy = cx = n // 2
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(yy - cy, xx - cx).astype(int)
    prof = np.bincount(r.ravel(), P.ravel()) / np.maximum(np.bincount(r.ravel()), 1)
    prof = prof[:n // 2]
    prof /= prof[1:].max()
    print("\nB. radial power spectrum (normalised; f as fraction of Nyquist)")
    print(f"   {'f/Nyq':>7} {'lp/mm':>8} {'power':>11}")
    for frac in (0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90, 0.99):
        i = int(frac * (len(prof) - 1))
        lpmm = frac * (dpi / 25.4) / 2.0
        print(f"   {frac:>7.2f} {lpmm:>8.1f} {prof[i]:>11.5f}")
    hi = prof[int(0.7 * len(prof)):].mean()
    lo = prof[int(0.05 * len(prof)):int(0.15 * len(prof))].mean()
    print(f"   high-band (0.7-1.0 Nyq) mean = {hi:.5f}; "
          f"low-band (0.05-0.15) = {lo:.5f}; ratio = {hi/max(lo,1e-12):.4f}")
    print("   flat-ish floor => real per-pixel sensor noise; "
          "collapse to ~0 => band-limited by resampling")

    # --- C. histogram ----------------------------------------------------
    q = np.rint(g).astype(int)
    lo_l, hi_l = q.min(), q.max()
    counts = np.bincount((q - lo_l).ravel())
    used = int((counts > 0).sum())
    span = int(hi_l - lo_l + 1)
    p = counts[counts > 0] / counts.sum()
    ent = float(-(p * np.log2(p)).sum())
    gaps = int((counts == 0).sum())
    print(f"\nC. histogram: levels {lo_l}..{hi_l} (span {span}), "
          f"{used} occupied, {gaps} interior gaps, entropy {ent:.3f} bits/px")

    # --- D. compressibility ---------------------------------------------
    raw = np.clip(g, 0, 255).astype(np.uint8).tobytes()
    ratio = len(gzip.compress(raw, 6)) / len(raw)
    print(f"D. gzip ratio {ratio:.4f}  "
          f"({'incompressible - real grain' if ratio > 0.75 else 'compressible - little independent grain'})")


for name, path, dpi, color in CAPS:
    try:
        g = blank_patch(path, dpi, color)
    except Exception as exc:  # pragma: no cover - diagnostic
        print(f"\n{name}: SKIPPED ({exc})")
        continue
    report(name, g, dpi)

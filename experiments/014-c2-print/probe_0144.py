#!/usr/bin/env python
"""014.4 pre-registered probe: sub-grain failure attribution (zero print).

Question (experiments/014-c2-print.md 014.4): are the 014.3 sub-grain
failures (6 mm 0/5, 8 mm 1/5) word INCOMPLETENESS (no complete (100,23)
word in the window -- fixable by F13 correlation placement) or GEOMETRY
(pitch/rotation unestimable on a small window -- not fixable by
correlation either)?

Three arms per (position x size), sizes 6/8/10 mm, scan C:
  arm 1  BLIND:  formats.acquire_scan on the small window alone
                 (detector="ctx", matching 014.3).
  arm 2  GENIE-GEOMETRY: geometry lifted from an ENCLOSING 25 mm lock
                 (declared stand-in for the pre-registration's "full-page
                 lock": 014.1 measured 40 mm windows FAIL from warp
                 accumulation at c2, so a 25 mm enclosing lock IS the best
                 available geometry); the standard full-strength word
                 decode (_decode_visible_tiles, t_full=13) on the central
                 sub-window's cells at the known absolute origin, plus
                 in-window pilot-cell BER (global blind detector).
  arm 3  ORACLE-POSITION correlation margin: at genie geometry, mismatch
                 fraction of the sub-window's pilot cells vs predicted
                 values at the TRUE offset and at ALL site-phase-compatible
                 decoy offsets (origin + 60*(dy,dx), on-page; ~1.9k >= the
                 pre-registered 1000). Gate: true < 0.15 AND all decoys
                 > 0.35.

Declared deviations from the 014.3 setup: exact 014.3 window positions were
inline/unrecorded -- positions here are deterministic scan fractions,
off-crease enforced via the enclosing lock's absolute coordinates
(|row-1673| > 30 cells for the largest sub-window).

Run from repo root: python experiments/014-c2-print/probe_0144.py \\
    --scan-dir <evidence>/scans
"""
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/014-c2-print"))
import tifffile

from paperholo import acquire, compose, formats
from paperholo.modulation import rng
import gen_e014

SEED = gen_e014.SEED
spec = gen_e014.make_spec()
CD = 2
layout = spec.pilot
plane = spec.plane
P = layout.period_cells
page_tiles = (spec.page_cells_yx[0] // P, spec.page_cells_yx[1] // P)
CPM = 600 / 25.4 / CD           # cells per mm (11.81 at c2@600)
PX_CELL = CD * 8                # scan px per cell at 4800 dpi

if "--scan-dir" not in sys.argv[:-1]:
    sys.exit(__doc__)
SCAN_DIR = Path(sys.argv[sys.argv.index("--scan-dir") + 1])  # evidence archive
SCAN = SCAN_DIR / "xerox-e014-A-canon-4800gray-C-flattened.tiff"
CREASE_ROW, CREASE_HALO = 1673, 30
ENCL_MM = 25
SIZES_MM = (6, 8, 10)
CANDIDATES = [(fy, fx) for fy in (0.3, 0.7) for fx in (0.2, 0.35, 0.5, 0.65, 0.8)]
N_POS = 5
GATE_TRUE, GATE_DECOY = 0.15, 0.35

payload_gt = rng(SEED, b"e014/payload").integers(
    0, 2, compose.payload_capacity(spec), dtype=np.uint8)
cp = compose.compose_page(payload_gt, spec, SEED, page=0)
GT, PM = cp.cell_values, cp.pilot_mask
H_PAGE, W_PAGE = GT.shape

arr = tifffile.TiffFile(str(SCAN)).pages[0].asarray(out="memmap")
Hs, Ws = arr.shape
print(f"scan C {Hs}x{Ws}px; page {H_PAGE}x{W_PAGE} cells; "
      f"tiles {page_tiles}; plane {plane}", flush=True)


def hard_grid(r):
    """Global-blind hard bits on the enclosing lock's settled grid."""
    img = r.norm.img[:, ::-1] if r.result.mirrored else r.norm.img
    img_c = np.ascontiguousarray(np.rot90(img, r.result.orientation_k))
    means = acquire.sample_cell_means(
        acquire._normalize_refl(img_c), r.result.grid, cell_dots=CD)
    hard, _ = acquire.cell_bits_blind(means)
    return hard


def oracle_margins(sub, aoy, aox, n):
    """Mismatch fraction vs predicted pilot values at the true offset and
    every site-phase-compatible on-page decoy (pure GT/PM slice compares --
    the site pattern is periodic mod P)."""
    true_m, decoys = None, []
    for dy in range(-(aoy // P), (H_PAGE - n - aoy) // P + 1):
        for dx in range(-(aox // P), (W_PAGE - n - aox) // P + 1):
            oy2, ox2 = aoy + P * dy, aox + P * dx
            m = PM[oy2:oy2 + n, ox2:ox2 + n]
            if m.sum() < 20:
                continue
            mm = float(np.mean(sub[m] != GT[oy2:oy2 + n, ox2:ox2 + n][m]))
            if dy == 0 and dx == 0:
                true_m = mm
            else:
                decoys.append(mm)
    return true_m, np.asarray(decoys)


rows = []
kept = 0
for fy, fx in CANDIDATES:
    if kept >= N_POS:
        break
    src = int(ENCL_MM * CPM) * PX_CELL
    y0, x0 = int(Hs * fy) - src // 2, int(Ws * fx) - src // 2
    if y0 < 0 or x0 < 0 or y0 + src > Hs or x0 + src > Ws:
        continue
    win = np.asarray(arr[y0:y0 + src, x0:x0 + src], np.float32)
    t0 = time.perf_counter()
    r = formats.acquire_scan(win, scan_dpi=4800.0)
    if not r.ok:
        print(f"({fy},{fx}): enclosing 25mm lock FAIL -- candidate skipped",
              flush=True)
        continue
    hard = hard_grid(r)
    oy, ox = r.result.cell_origin_abs_yx
    Hc, Wc = hard.shape
    nmax = int(round(SIZES_MM[-1] * CPM))
    a_lo = oy + (Hc - nmax) // 2
    if abs(a_lo - CREASE_ROW) < CREASE_HALO + nmax and \
       abs(a_lo + nmax - CREASE_ROW) < CREASE_HALO + nmax and \
       a_lo <= CREASE_ROW + CREASE_HALO and CREASE_ROW - CREASE_HALO <= a_lo + nmax:
        print(f"({fy},{fx}): on-crease (rows {a_lo}..{a_lo+nmax}) -- skipped",
              flush=True)
        continue
    kept += 1
    print(f"\n== position {kept} ({fy},{fx}) abs origin ({oy},{ox}) "
          f"lock {time.perf_counter()-t0:.1f}s ==", flush=True)
    for mm_sz in SIZES_MM:
        n = int(round(mm_sz * CPM))
        cy0, cx0 = (Hc - n) // 2, (Wc - n) // 2
        aoy, aox = oy + cy0, ox + cx0
        sub = hard[cy0:cy0 + n, cx0:cx0 + n]

        # arm 1 -- blind small window
        s1 = n * PX_CELL
        yy0 = y0 + src // 2 - s1 // 2
        xx0 = x0 + src // 2 - s1 // 2
        win1 = np.asarray(arr[yy0:yy0 + s1, xx0:xx0 + s1], np.float32)
        r1 = formats.acquire_scan(win1, scan_dpi=4800.0, detector="ctx")
        if r1.ok:
            idx = r1.result.payload_cell_index
            ber1 = 100 * float(np.mean(r1.result.payload_bits
                                       != payload_gt[idx]))
            blind = f"OK {ber1:.2f}%"
        else:
            blind = "FAIL"

        # arm 2 -- genie-geometry standard word decode on the sub-window
        n_att, n_dec, n_err, per_tile = acquire._decode_visible_tiles(
            sub, layout, SEED, plane, 0, (aoy, aox), page_tiles)
        m0 = PM[aoy:aoy + n, aox:aox + n]
        pber = 100 * float(np.mean(sub[m0] != GT[aoy:aoy + n,
                                                 aox:aox + n][m0]))

        # arm 3 -- oracle-position correlation margin
        true_m, dec = oracle_margins(sub, aoy, aox, n)
        gate = (true_m is not None and true_m < GATE_TRUE
                and dec.size >= 1000 and float(dec.min()) > GATE_DECOY)

        rows.append(dict(pos=kept, mm=mm_sz, n=n, blind=blind,
                         n_att=n_att, n_dec=n_dec, pber=pber,
                         true_m=true_m, dec_min=float(dec.min()),
                         dec_med=float(np.median(dec)), n_dec_hyp=dec.size,
                         gate=gate, sites=int(m0.sum())))
        print(f"  {mm_sz:2d}mm ({n:3d} cells, {int(m0.sum()):3d} pilot "
              f"sites): blind {blind:<10s} | genie words {n_dec}/{n_att} "
              f"pilotBER {pber:5.2f}% | margin true {true_m:.3f} decoys "
              f"min {dec.min():.3f} med {np.median(dec):.3f} "
              f"(n={dec.size}) gate {'PASS' if gate else 'FAIL'}",
              flush=True)

print("\n=== 014.4 pre-registered decision table ===", flush=True)
for mm_sz in SIZES_MM:
    rs = [r for r in rows if r["mm"] == mm_sz]
    blind_ok = sum("OK" in r["blind"] for r in rs)
    genie_ok = sum(r["n_dec"] >= 1 for r in rs)
    full_vis = sum(r["n_att"] >= 1 for r in rs)
    gate_ok = sum(r["gate"] for r in rs)
    print(f"{mm_sz:2d}mm: blind {blind_ok}/{len(rs)} | full tile visible "
          f"{full_vis}/{len(rs)} | genie word-decode {genie_ok}/{len(rs)} "
          f"| oracle margin gate {gate_ok}/{len(rs)}", flush=True)
print("""
rules: genie >=4/5 at 6-8mm  -> failures were GEOMETRIC (F13 needs a
                                geometry assist first)
       words fail + gate pass -> WORD INCOMPLETENESS (F13 viable as specced)
       neither                -> below the physical floor; move the §14
                                boundary up, RaptorQ absorbs""", flush=True)

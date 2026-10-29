#!/usr/bin/env python
"""014.4 POST-HOC diagnostic (labeled as such in the log): attribute the
pre-registered min-decoy gate failures. Hypothesis: the low-mismatch decoy
tail is edge-clipped hypotheses with tiny pilot-site support (the >=20-site
floor admits decoys whose binomial sd is ~0.11), not genuine confusability.
Re-runs arm 3 recording per-decoy site counts; reports the decoy minimum
stratified by support and each decoy's binomial z-score against 0.5.
Primary-arm values are untouched (deterministic; same positions as
probe_0144.py).

Run from repo root: python experiments/014-c2-print/probe_0144_posthoc.py \\
    --scan-dir <evidence>/scans
"""
import sys
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
P = spec.pilot.period_cells
CPM = 600 / 25.4 / CD
PX_CELL = CD * 8
if "--scan-dir" not in sys.argv[:-1]:
    sys.exit(__doc__)
SCAN_DIR = Path(sys.argv[sys.argv.index("--scan-dir") + 1])  # evidence archive
SCAN = SCAN_DIR / "xerox-e014-A-canon-4800gray-C-flattened.tiff"
CANDIDATES = [(0.3, fx) for fx in (0.2, 0.35, 0.5, 0.65, 0.8)]
SIZES_MM = (6, 8, 10)

payload_gt = rng(SEED, b"e014/payload").integers(
    0, 2, compose.payload_capacity(spec), dtype=np.uint8)
cp = compose.compose_page(payload_gt, spec, SEED, page=0)
GT, PM = cp.cell_values, cp.pilot_mask
H_PAGE, W_PAGE = GT.shape

arr = tifffile.TiffFile(str(SCAN)).pages[0].asarray(out="memmap")
Hs, Ws = arr.shape

for fy, fx in CANDIDATES:
    src = int(25 * CPM) * PX_CELL
    y0, x0 = int(Hs * fy) - src // 2, int(Ws * fx) - src // 2
    win = np.asarray(arr[y0:y0 + src, x0:x0 + src], np.float32)
    r = formats.acquire_scan(win, scan_dpi=4800.0)
    if not r.ok:
        continue
    img = r.norm.img[:, ::-1] if r.result.mirrored else r.norm.img
    img_c = np.ascontiguousarray(np.rot90(img, r.result.orientation_k))
    means = acquire.sample_cell_means(
        acquire._normalize_refl(img_c), r.result.grid, cell_dots=CD)
    hard, _ = acquire.cell_bits_blind(means)
    oy, ox = r.result.cell_origin_abs_yx
    Hc, Wc = hard.shape
    for mm_sz in SIZES_MM:
        n = int(round(mm_sz * CPM))
        cy0, cx0 = (Hc - n) // 2, (Wc - n) // 2
        aoy, aox = oy + cy0, ox + cx0
        sub = hard[cy0:cy0 + n, cx0:cx0 + n]
        true_sites = int(PM[aoy:aoy + n, aox:aox + n].sum())
        mis, cnt = [], []
        for dy in range(-(aoy // P), (H_PAGE - n - aoy) // P + 1):
            for dx in range(-(aox // P), (W_PAGE - n - aox) // P + 1):
                if dy == 0 and dx == 0:
                    continue
                oy2, ox2 = aoy + P * dy, aox + P * dx
                m = PM[oy2:oy2 + n, ox2:ox2 + n]
                k = int(m.sum())
                if k < 20:
                    continue
                mis.append(float(np.mean(
                    sub[m] != GT[oy2:oy2 + n, ox2:ox2 + n][m])))
                cnt.append(k)
        mis, cnt = np.asarray(mis), np.asarray(cnt)
        z = (0.5 - mis) * np.sqrt(cnt) / 0.5      # binomial z vs fair coin
        full = cnt >= true_sites // 2
        print(f"({fy},{fx}) {mm_sz:2d}mm: true_sites {true_sites:3d} | "
              f"decoys n={mis.size} minALL {mis.min():.3f} "
              f"(support {cnt[np.argmin(mis)]:3d}) | "
              f"min@>=50%support {mis[full].min():.3f} "
              f"(n={int(full.sum())}) | max z {z.max():.1f}sigma "
              f"(support {cnt[np.argmax(z)]:3d})", flush=True)

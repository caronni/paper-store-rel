#!/usr/bin/env python
"""e026: pilot-density subsample probe (zero print) — grain(δ) below 2.78%.

Measures the F13 correlation-placement floor as a function of pilot site
density by THINNING THE PREDICTED FIELD (probe-side wrap of
place.pilot_field; src untouched) and re-running the exact 014.5 window
harness on the real e014 Canon scans. Pre-registration + scope limits:
experiments/026-pilot-density-subsample.md (control must reproduce the
014.5/016.7 floor before any thinned row counts; zero false placements
expected everywhere; site-count law predicts floor ~ 1/sqrt(f)).

Run from repo root:
  env/bin/python experiments/026-pilot-density-subsample/probe_e026.py \\
      --scan-root <evidence>/scans [--quick] [--c3]
(the e012/e014 Canon captures are in the evidence archive)
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/014-c2-print"))
sys.path.insert(0, str(ROOT / "experiments/012-pilot-print"))
import tifffile

from paperholo import acquire, formats, place, scannorm  # noqa: E402

QUICK = "--quick" in sys.argv
C3 = "--c3" in sys.argv          # 026.1 replication arm: e012 c3 intact sheet
if "--scan-root" not in sys.argv[:-1]:
    sys.exit(__doc__)
SCAN_ROOT = Path(sys.argv[sys.argv.index("--scan-root") + 1])
if C3:
    import gen_e012 as _gen  # noqa: E402
    CD = 3
    SCANS = (("A", SCAN_ROOT / "xerox-e012-A-canon-4800.tiff",
              ((0.3, 0.3), (0.3, 0.55), (0.3, 0.75), (0.55, 0.4),
               (0.7, 0.35), (0.7, 0.65))),)
else:
    import gen_e014 as _gen  # noqa: E402
    CD = 2
    SCANS = (("C", SCAN_ROOT / "xerox-e014-A-canon-4800gray-C-flattened.tiff",
              ((0.3, 0.2), (0.3, 0.35), (0.3, 0.5), (0.3, 0.65), (0.3, 0.8))),
             ("B", SCAN_ROOT / "xerox-e014-A-canon-4800gray-B-displaced.tiff",
              ((0.3, 0.3), (0.3, 0.6), (0.7, 0.4))))
SEED = _gen.SEED
spec = _gen.make_spec()
CPM = 600 / 25.4 / CD          # cells per mm
PX_CELL = CD * 8               # 4800 dpi grey: 8 px/dot
SIZES_MM = (5, 6, 8) if QUICK else (4, 5, 6, 8, 10, 12)
FRACTIONS = (1.00, 0.64) if QUICK else (1.00, 0.80, 0.64, 0.44, 0.36)
# NOTE (026.1): only P = 10*B is constructible under the frozen quota
# lattice ((P/B)^2 = 100 sites/word is glued to the (127,50)->(100,23)
# code); 67/75 are idealized labels, real rungs are 60/70/80/90/100.
P_EQUIV = {1.00: 60, 0.80: 67, 0.64: 75, 0.44: 90, 0.36: 100}
SUBPOS = ((0.25, 0.25), (0.25, 0.75), (0.75, 0.25), (0.75, 0.75))
OUT = (ROOT / "experiments/026-pilot-density-subsample/build/"
       f"e026_report{'_c3' if C3 else ''}.json")

# --- deterministic per-site thinning (probe-side experimental variable; ---
# --- position-keyed blake2b, order-independent, nested across fractions ---
_orig_pilot_field = place.pilot_field
_STATE = {"f": 1.0}
_THIN: dict[tuple, np.ndarray] = {}


def _site_u(ys: np.ndarray, xs: np.ndarray) -> np.ndarray:
    u = np.empty(ys.size, np.float64)
    for i, (y, x) in enumerate(zip(ys.tolist(), xs.tolist())):
        d = hashlib.blake2b(
            b"e026/keep" + int(y).to_bytes(4, "little")
            + int(x).to_bytes(4, "little"), digest_size=8).digest()
        u[i] = int.from_bytes(d, "little") / 2.0 ** 64
    return u


def _thinned_field(spec_, seed_, page_):
    vals, mask = _orig_pilot_field(spec_, seed_, page_)
    f = _STATE["f"]
    if f >= 1.0:
        return vals, mask
    key = (seed_, spec_.plane, page_, round(f, 4))
    if key not in _THIN:
        ys, xs = np.nonzero(mask)
        drop = _site_u(ys, xs) >= f
        m = mask.copy()
        m[ys[drop], xs[drop]] = False
        _THIN[key] = m
    return vals, _THIN[key]


place.pilot_field = _thinned_field


def enclosing(arr, Hs, Ws, fy, fx):
    """014.5 verbatim: 25 mm blind lock -> ctx hard bits + absolute origin."""
    src = int(25 * CPM) * PX_CELL
    y0, x0 = int(Hs * fy) - src // 2, int(Ws * fx) - src // 2
    win = np.asarray(arr[y0:y0 + src, x0:x0 + src], np.float32)
    if win.ndim == 3:              # RGB scan: luma reduce, crop only
        win = win.mean(axis=2)
    r = formats.acquire_scan(win, scan_dpi=4800.0)
    if not r.ok:
        return None
    img = r.norm.img[:, ::-1] if r.result.mirrored else r.norm.img
    img_c = np.ascontiguousarray(np.rot90(img, r.result.orientation_k))
    means = acquire.sample_cell_means(
        acquire._normalize_refl(img_c), r.result.grid, cell_dots=CD)
    hard_c, _ = acquire.cell_bits_ctx(means)
    return dict(oy=r.result.cell_origin_abs_yx[0],
                ox=r.result.cell_origin_abs_yx[1], hard_c=hard_c)


def main():
    t_all = time.perf_counter()
    locks = []
    for si, (tag, path, poss) in enumerate(SCANS):
        if QUICK and si > 0:
            continue
        arr = tifffile.TiffFile(str(path)).pages[0].asarray(out="memmap")
        Hs, Ws = arr.shape[:2]
        for fy, fx in (poss[:2] if QUICK else poss):
            L = enclosing(arr, Hs, Ws, fy, fx)
            print(f"lock {tag}({fy},{fx}): {'ok' if L else 'FAIL'}",
                  flush=True)
            if L:
                L["tag"] = f"{tag}({fy},{fx})"
                locks.append(L)
    _orig_pilot_field(spec, SEED, 0)   # warm the true-field cache

    records = []
    summary = []
    for f in FRACTIONS:
        _STATE["f"] = f
        _, thin = _thinned_field(spec, SEED, 0)
        eff = float(thin.mean())
        for mm in SIZES_MM:
            n = int(round(mm * CPM))
            t0 = time.perf_counter()
            rows = []
            for L in locks:
                Hc, Wc = L["hard_c"].shape
                subs = SUBPOS[:2] if QUICK else SUBPOS
                for qy, qx in subs:
                    cy0 = min(max(int(Hc * qy) - n // 2, 0), Hc - n)
                    cx0 = min(max(int(Wc * qx) - n // 2, 0), Wc - n)
                    sub = L["hard_c"][cy0:cy0 + n, cx0:cx0 + n]
                    aoy, aox = L["oy"] + cy0, L["ox"] + cx0
                    sites = int(thin[aoy:aoy + n, aox:aox + n].sum())
                    pl = place.place_fragment(sub, spec, SEED)
                    exact = (pl.page == 0 and pl.rot_k == 0
                             and pl.origin_yx == (aoy, aox))
                    near = (pl.page == 0 and pl.rot_k == 0
                            and pl.origin_yx is not None
                            and abs(pl.origin_yx[0] - aoy) <= 1
                            and abs(pl.origin_yx[1] - aox) <= 1)
                    sess = (pl.mismatch < 0.20
                            and (pl.rival_mismatch - pl.mismatch) >= 0.08)
                    rows.append(dict(
                        tag=L["tag"], mm=mm, f=f, sites=sites,
                        exact=bool(exact), near=bool(near),
                        gate=bool(pl.ok), sess=bool(sess),
                        mism=round(pl.mismatch, 4),
                        rival=round(pl.rival_mismatch, 4),
                        z_gap=round(float(pl.z_gap), 2)))
            records.extend(rows)
            nw = len(rows)
            ex = sum(r["exact"] for r in rows)
            gt = sum(r["exact"] and r["gate"] for r in rows)
            ss = sum(r["exact"] and r["sess"] for r in rows)
            fa = sum((r["gate"] or r["sess"]) and not r["near"] for r in rows)
            ref = sum(not r["gate"] and not r["sess"] for r in rows)
            ms = np.mean([r["sites"] for r in rows])
            dt = time.perf_counter() - t0
            line = (f"f={f:.2f} (P~{P_EQUIV[f]:3d}, deff {100*eff:.2f}%) "
                    f"{mm:2d}mm: exact {ex:2d}/{nw} frozen-gate {gt:2d} "
                    f"sess-gate {ss:2d} FALSE {fa} refuse {ref:2d} "
                    f"| ~{ms:5.0f} sites/win | {dt/nw:.1f}s/frag")
            print(line, flush=True)
            summary.append(dict(f=f, p_equiv=P_EQUIV[f], mm=mm, n=nw,
                                exact=ex, gate_pass=gt, sess_pass=ss,
                                false_place=fa, refuse=ref,
                                mean_sites=round(float(ms), 1)))

    # nulls at the thinnest density: wrong seed must refuse
    _STATE["f"] = FRACTIONS[-1]
    nulls = []
    for mm in (6, 10):
        n = int(round(mm * CPM))
        L = locks[0]
        Hc, Wc = L["hard_c"].shape
        sub = L["hard_c"][(Hc - n) // 2:(Hc - n) // 2 + n,
                          (Wc - n) // 2:(Wc - n) // 2 + n]
        pl = place.place_fragment(sub, spec, b"e026-wrong-seed-null")
        nulls.append(dict(mm=mm, gate=bool(pl.ok),
                          mism=round(pl.mismatch, 4)))
        print(f"wrong-seed null f={FRACTIONS[-1]} {mm}mm: gate {pl.ok} "
              f"(must be False) mism {pl.mismatch:.3f}", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(
        quick=QUICK, sizes_mm=SIZES_MM, fractions=FRACTIONS,
        n_locks=len(locks), summary=summary, nulls=nulls,
        records=records), indent=1))
    print(f"\nreport -> {OUT}  ({time.perf_counter()-t_all:.0f}s total)",
          flush=True)


if __name__ == "__main__":
    main()

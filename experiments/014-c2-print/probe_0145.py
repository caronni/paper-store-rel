#!/usr/bin/env python
"""014.5 qualification probe (zero print): the two F13-adjacent builds on
real toner — (1) the ERASURE RUNG (§14): partial-pilot-tile word decode via
bch.decode_erasures on real detected bits, success vs visible fraction q,
global vs ctx detector, edge-geometric vs random cuts, vs the verified
arithmetic prediction (ctx: q=0.85 reliable / 0.80 marginal; global ~8%:
dead below q~0.90); (2) the F13 PLACER (§15): place_fragment on genie-bit
sub-windows (4-10 mm) against the FULL page, rot recovery, wrong-seed and
wrong-region nulls, pending-mask pruning; (3) ISOLATED end-to-end: crop ->
own pitch measure -> own lattice lock -> ctx bits -> place (no enclosing
geometry — the §15.5 item-2 unknown); (4) FRESH-WINDOW gate validation on
scan B (§15.4 iii — constants 0.15/0.20 were set on scan C).

Run from repo root: env/bin/python experiments/014-c2-print/probe_0145.py \\
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

from paperholo import acquire, bch, compose, formats, pilots, place, scannorm
from paperholo.modulation import rng
import gen_e014

SEED = gen_e014.SEED
spec = gen_e014.make_spec()
CD = 2
P = spec.pilot.period_cells
page_tiles = (spec.page_cells_yx[0] // P, spec.page_cells_yx[1] // P)
GEO = {"tiles_x": page_tiles[1],
       "tiles_per_page": page_tiles[0] * page_tiles[1]}
CPM = 600 / 25.4 / CD
PX_CELL = CD * 8
POS_TILE = pilots.site_positions_tile(spec.pilot, SEED)

payload_gt = rng(SEED, b"e014/payload").integers(
    0, 2, compose.payload_capacity(spec), dtype=np.uint8)
cp = compose.compose_page(payload_gt, spec, SEED, page=0)
GT, PM = cp.cell_values, cp.pilot_mask

if "--scan-dir" not in sys.argv[:-1]:
    sys.exit(__doc__)
SCAN_DIR = Path(sys.argv[sys.argv.index("--scan-dir") + 1])  # evidence archive
SCAN_C = SCAN_DIR / "xerox-e014-A-canon-4800gray-C-flattened.tiff"
SCAN_B = SCAN_DIR / "xerox-e014-A-canon-4800gray-B-displaced.tiff"
CANDS = [(0.3, fx) for fx in (0.2, 0.35, 0.5, 0.65, 0.8)]
QS = (0.70, 0.75, 0.80, 0.85, 0.90, 0.95)


def enclosing(arr, Hs, Ws, fy, fx):
    src = int(25 * CPM) * PX_CELL
    y0, x0 = int(Hs * fy) - src // 2, int(Ws * fx) - src // 2
    win = np.asarray(arr[y0:y0 + src, x0:x0 + src], np.float32)
    r = formats.acquire_scan(win, scan_dpi=4800.0)
    if not r.ok:
        return None
    img = r.norm.img[:, ::-1] if r.result.mirrored else r.norm.img
    img_c = np.ascontiguousarray(np.rot90(img, r.result.orientation_k))
    means = acquire.sample_cell_means(
        acquire._normalize_refl(img_c), r.result.grid, cell_dots=CD)
    hard_g, _ = acquire.cell_bits_blind(means)
    hard_c, _ = acquire.cell_bits_ctx(means)
    return dict(oy=r.result.cell_origin_abs_yx[0],
                ox=r.result.cell_origin_abs_yx[1],
                hard_g=hard_g, hard_c=hard_c, y0=y0, x0=x0, src=src)


arr = tifffile.TiffFile(str(SCAN_C)).pages[0].asarray(out="memmap")
Hs, Ws = arr.shape
locks = []
for fy, fx in CANDS:
    L = enclosing(arr, Hs, Ws, fy, fx)
    print(f"lock ({fy},{fx}): {'ok' if L else 'FAIL'}", flush=True)
    if L:
        locks.append(L)

# ---- PART 1: erasure rung on real detected bits --------------------------
print("\n== PART 1: erasure-rung word decode, real bits ==", flush=True)
gen = rng(SEED, b"probe0145/cuts")
stats: dict[tuple, list[int]] = {}
wrong = 0
for L in locks:
    for det in ("global", "ctx"):
        hard = L["hard_g"] if det == "global" else L["hard_c"]
        Hc, Wc = hard.shape
        ty0, tx0 = -(-L["oy"] // P), -(-L["ox"] // P)
        for ty in range(ty0, (L["oy"] + Hc) // P):
            for tx in range(tx0, (L["ox"] + Wc) // P):
                ly, lx = ty * P - L["oy"], tx * P - L["ox"]
                word = hard[ly + POS_TILE[:, 0], lx + POS_TILE[:, 1]]
                for q in QS:
                    for cut in ("edge", "rand"):
                        if cut == "edge":
                            thr = np.quantile(POS_TILE[:, 0], q)
                            era = np.flatnonzero(POS_TILE[:, 0] > thr)
                        else:
                            era = gen.permutation(100)[:round(100 * (1 - q))]
                        info = pilots.decode_word(
                            word, spec.pilot, SEED, spec.plane,
                            bch.CODE_V3.t_full, erasures=era, **GEO)
                        okd = (info is not None and info["page"] == 0
                               and (info["ptile_y"], info["ptile_x"])
                               == (ty, tx))
                        if info is not None and not okd:
                            wrong += 1
                        stats.setdefault((det, q, cut), []).append(int(okd))
print(f"{'det':7s} {'q':>5s}  edge-cut       random-cut", flush=True)
for det in ("global", "ctx"):
    for q in QS:
        e = stats[(det, q, "edge")]
        r_ = stats[(det, q, "rand")]
        print(f"{det:7s} {q:5.2f}  {sum(e):3d}/{len(e):3d} "
              f"({100*np.mean(e):5.1f}%)  {sum(r_):3d}/{len(r_):3d} "
              f"({100*np.mean(r_):5.1f}%)", flush=True)
print(f"WRONG-address decodes (must be ~0): {wrong}", flush=True)

# ---- PART 2: placer on genie-geometry bits -------------------------------
print("\n== PART 2: placer, genie bits, full-page hypothesis space ==",
      flush=True)
place.pilot_field(spec, SEED, 0)   # warm the cache outside timing
for mm in (4, 5, 6, 8, 10):
    n = int(round(mm * CPM))
    res = []
    t0 = time.perf_counter()
    for L in locks:
        Hc, Wc = L["hard_g"].shape
        cy0, cx0 = (Hc - n) // 2, (Wc - n) // 2
        aoy, aox = L["oy"] + cy0, L["ox"] + cx0
        for det, hard in (("g", L["hard_g"]), ("c", L["hard_c"])):
            sub = hard[cy0:cy0 + n, cx0:cx0 + n]
            pl = place.place_fragment(sub, spec, SEED)
            hit = pl.origin_yx == (aoy, aox) and pl.rot_k == 0
            res.append((det, hit, pl.ok, pl.mismatch, pl.rival_mismatch,
                        pl.z_gap))
    dt = (time.perf_counter() - t0) / len(res)
    for det in ("g", "c"):
        rs = [r for r in res if r[0] == det]
        hits = sum(r[1] for r in rs)
        gates = sum(r[1] and r[2] for r in rs)
        mm_max = max(r[3] for r in rs)
        rv_min = min(r[4] for r in rs)
        zg_min = min(r[5] for r in rs if r[1])
        print(f"{mm:2d}mm det={det}: correct {hits}/{len(rs)} gate-PASS "
              f"{gates}/{len(rs)} | worst mism {mm_max:.3f} min rival "
              f"{rv_min:.3f} min z-gap {zg_min:5.1f} | {dt:.2f}s/frag",
              flush=True)
# rotation recovery + nulls at 6 mm
n = int(round(6 * CPM))
L = locks[0]
Hc, Wc = L["hard_c"].shape
cy0, cx0 = (Hc - n) // 2, (Wc - n) // 2
sub = L["hard_c"][cy0:cy0 + n, cx0:cx0 + n]
aoy, aox = L["oy"] + cy0, L["ox"] + cx0
for k in (1, 2, 3):
    pl = place.place_fragment(np.rot90(sub, -k), spec, SEED)
    print(f"rot k={k}: recovered rot_k={pl.rot_k} origin-ok "
          f"{pl.origin_yx == (aoy, aox)} gate {pl.ok}", flush=True)
pl = place.place_fragment(sub, spec, b"wrong-seed-null")
print(f"wrong-seed null: gate {pl.ok} (must be False) best mism "
      f"{pl.mismatch:.3f}", flush=True)
pm = np.zeros(tuple(spec.page_cells_yx), bool)
pm[:600, :600] = True   # excludes the true region
pl = place.place_fragment(sub, spec, SEED, pending_cell_mask={0: pm})
print(f"wrong-region pending null: gate {pl.ok} (must be False)",
      flush=True)
pm2 = np.zeros(tuple(spec.page_cells_yx), bool)
pm2[aoy - 90:aoy + 90, aox - 90:aox + 90] = True
t0 = time.perf_counter()
pl = place.place_fragment(sub, spec, SEED, pending_cell_mask={0: pm2})
print(f"pruned-to-region: origin-ok {pl.origin_yx == (aoy, aox)} "
      f"{time.perf_counter()-t0:.2f}s", flush=True)

# ---- PART 3: ISOLATED end-to-end (own lock, no enclosing geometry) -------
print("\n== PART 3: isolated pieces — own pitch + own lock + place ==",
      flush=True)
for mm in (5, 6, 8, 10):
    n = int(round(mm * CPM))
    ok_n = 0
    tried = 0
    for L in locks:
        s1 = n * PX_CELL
        yy0 = L["y0"] + L["src"] // 2 - s1 // 2
        xx0 = L["x0"] + L["src"] // 2 - s1 // 2
        crop = np.asarray(arr[yy0:yy0 + s1, xx0:xx0 + s1], np.float32)
        tried += 1
        try:
            pit = scannorm.measure_cell_pitch(crop)
            norm = scannorm.normalize_to_canonical(crop, pit.pitch_px, CD)
            grid = acquire.lock_grid(norm.img,
                                     cell_px_nominal=norm.cell_px_est,
                                     cell_dots=CD)
            means = acquire.sample_cell_means(
                acquire._normalize_refl(norm.img), grid, cell_dots=CD)
            hard, _ = acquire.cell_bits_ctx(means)
        except Exception as ex:  # pitch/lock refusals ARE the measurement
            print(f"  {mm}mm pos{tried}: local lock FAIL "
                  f"({type(ex).__name__}: {str(ex)[:60]})", flush=True)
            continue
        pl = place.place_fragment(hard, spec, SEED)
        # verdict by GT: payload BER at the placed origin
        verdict = "no-place"
        if pl.origin_yx is not None:
            oy, ox = pl.origin_yx
            hh, ww = hard.shape if pl.rot_k % 2 == 0 else hard.shape[::-1]
            hb = np.rot90(hard, pl.rot_k)
            g = GT[oy:oy + hh, ox:ox + ww]
            if g.shape == hb.shape:
                ber = float(np.mean(hb != g))
                good = ber < 0.20
                ok_n += int(good and pl.ok)
                verdict = (f"BER {100*ber:4.1f}% gate "
                           f"{'PASS' if pl.ok else 'fail'} mism "
                           f"{pl.mismatch:.3f}")
        print(f"  {mm}mm pos{tried}: {verdict}", flush=True)
    print(f"{mm}mm isolated end-to-end: {ok_n}/{tried} placed+gated+correct",
          flush=True)

# ---- PART 4: fresh-window gate validation on scan B (§15.4 iii) ----------
print("\n== PART 4: scan B fresh windows (gate constants were set on C) ==",
      flush=True)
arrB = tifffile.TiffFile(str(SCAN_B)).pages[0].asarray(out="memmap")
HsB, WsB = arrB.shape
for fy, fx in ((0.3, 0.3), (0.3, 0.6), (0.7, 0.4)):
    L = enclosing(arrB, HsB, WsB, fy, fx)
    if L is None:
        print(f"B ({fy},{fx}): enclosing lock FAIL", flush=True)
        continue
    for mm in (6, 8):
        n = int(round(mm * CPM))
        Hc, Wc = L["hard_c"].shape
        cy0, cx0 = (Hc - n) // 2, (Wc - n) // 2
        sub = L["hard_c"][cy0:cy0 + n, cx0:cx0 + n]
        aoy, aox = L["oy"] + cy0, L["ox"] + cx0
        pl = place.place_fragment(sub, spec, SEED)
        print(f"B ({fy},{fx}) {mm}mm: correct "
              f"{pl.origin_yx == (aoy, aox)} gate "
              f"{'PASS' if pl.ok else 'FAIL'} mism {pl.mismatch:.3f} "
              f"rival {pl.rival_mismatch:.3f} z-gap {pl.z_gap:.1f}",
              flush=True)
print("\ndone", flush=True)

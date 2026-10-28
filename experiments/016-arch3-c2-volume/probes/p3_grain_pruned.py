#!/usr/bin/env python
"""P3 item 2 — session-state grain (pre-registered zero-print probe).

Question: 014.3 measured the c2 confetti grain with a FULL-page blind
search (10 mm 5/5, 8 mm 1/5, 6 mm 0/5); 014.5's F13 placer has a gated
floor of 5 mm. How far below the full-page grain does a SHRUNKEN pending
set (the F13 decode-state pruning a real session provides) push the
usable-piece floor?

Design (pre-registered, see the kickoff prompt / 016.4 log):
  - source scratch/e016c2hp-canon4800gray.tiff (scan A, sha 593742f6...),
    field bbox via gen_confetti_session.field_bbox, 2x2 box-decimate
    crops to 2400 dpi (8 px/cell), e016 c2 spec + volume seed;
  - sizes 4/5/6/8/10 mm, UNROTATED (014.3 comparability), N=10
    seeded-random interior positions per size (outer 10 mm rim avoided);
  - pending fractions 1.00/0.50/0.20/0.08 of the page's 1820 LDPC tiles:
    pending = the piece's OWN overlapping tiles (the truth is pending by
    session construction) UNION a seeded-random subset of all OTHER
    tiles at the fraction; cell mask built exactly like
    session_decode.py (64-cell tiles -> bool page mask, pend={0: pm});
  - placement: place.place_fragment(gate_true=0.20, gate_decoy=0.20)
    + the session gap rule rival_mismatch - mismatch >= 0.08;
  - per (size, fraction) cell: usable = admission rate with ZERO false
    placements; ANY admitted-but-wrong placement is CRITICAL.

DECLARED DEVIATIONS from the design-as-written (both measured before the
sweep, neither touches the pre-registered axes):
  D1  Detection runs the full session piece path from
      session_decode.piece_bits (scannorm.measure_cell_pitch ->
      normalize_to_canonical -> segment.piece_cell_bits), NOT
      piece_cell_bits directly on the raw decimated crop. The raw crop
      carries the Canon +0.4% scale (pitch ~7.97 px/cell): one integer
      phase cannot hold across a piece, a pure footing artifact (25 mm
      calibration crop mismatch 0.287 raw vs ~0.12-0.15 normalized).
      The session a real piece would ride normalizes first; this probe
      measures session-state grain, so it does too.
  D2  field_bbox's x1 hits the scan's right edge (dark edge artifact:
      bbox reads 205 mm wide vs the true 188 mm field). Position
      sampling extent + expected origins therefore come from a 5-point
      calibration fit (12 mm crops at fixed positions, full-page
      unpruned placement under the FROZEN 0.15/0.20 gates), AFFINE
      px->cell per axis — the glass placement carries ~0.23 deg skew,
      so a per-axis linear fit is wrong by up to 4.5 cells (measured);
      residuals gated <= 2 cells. The bbox itself is still computed
      and recorded as designed.

All randomness: paperholo.modulation.rng(gen_e016.SEED,
b"e016/p3-grain-pruned/v1"), consumed in one documented order
(positions for all sizes first, then one subset draw per
(size, position, fraction) triple, detection-independent).

Output: experiments/016-arch3-c2-volume/build/p3_grain_pruned.json
(per-trial rows + per-cell aggregates). Run from anywhere:
  env/bin/python experiments/016-arch3-c2-volume/probes/p3_grain_pruned.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/016-arch3-c2-volume"))

import tifffile                                           # noqa: E402

import gen_confetti_session as gcs                        # noqa: E402
import gen_e016                                           # noqa: E402
from paperholo import compose, formats, fountain          # noqa: E402
from paperholo import ldpc, place, scannorm, segment      # noqa: E402
from paperholo.modulation import rng                      # noqa: E402

SEED = gen_e016.SEED
RNG_LABEL = b"e016/p3-grain-pruned/v1"
SCAN = ROOT / "scratch/e016c2hp-canon4800gray.tiff"
OUT = ROOT / "experiments/016-arch3-c2-volume/build/p3_grain_pruned.json"

SIZES_MM = (4, 5, 6, 8, 10)
FRACTIONS = (1.00, 0.50, 0.20, 0.08)
N_POS = 10                     # pre-registered N (drop to 6 = declared fallback)
RIM_MM = 10.0                  # interior sampling: avoid the outer rim
GATE_TRUE = 0.20               # session gap-gate constants (016.4)
GATE_DECOY = 0.20
GAP_MIN = 0.08
TOL_CELLS = 3                  # |placed - expected| correctness tolerance
AGREE_MIN = 0.70               # GT-bit agreement corroboration bar
TILE = 64                      # LDPC tile side, cells
MM_SRC = gcs.MM_SRC            # 4800-dpi px per mm

# calibration crops (D2): fixed field-fraction positions, 12 mm each.
# 5 spread points because the mapping is AFFINE, not per-axis linear: the
# glass placement carries ~0.23 deg skew (measured on this scan — a 3-point
# per-axis fit left 4.5-cell x residuals whose pattern is exactly a
# px_y-dependent x term; the cross-term recovers pitch 15.97 px/cell clean).
CAL_MM = 12
CAL_FRACS = ((0.15, 0.20), (0.15, 0.75), (0.50, 0.45),
             (0.85, 0.25), (0.85, 0.75))

FMT = next(f for f in formats.FORMAT_REGISTRY if f.format_id == "e016-v3-c2")


def crop_decimated(arr: np.ndarray, sy0: int, sx0: int, n_px: int
                   ) -> np.ndarray:
    """Source crop @4800 -> float grey -> 2x2 box decimate to 2400 dpi."""
    crop = np.asarray(arr[sy0:sy0 + n_px, sx0:sx0 + n_px], np.float32)
    if arr.dtype == np.uint16:
        crop /= 257.0
    h2 = (crop.shape[0] // 2) * 2
    w2 = (crop.shape[1] // 2) * 2
    return crop[:h2, :w2].reshape(h2 // 2, 2, w2 // 2, 2).mean(axis=(1, 3))


def detect(dec: np.ndarray, cell_dots: int):
    """Session piece path (D1) = session_decode.piece_bits sans piece mask
    (razor-cut rect crops are all field): own pitch -> canonical footing ->
    phase-searched cell lock. Returns (bits, cell mask, pitch, cell_px)."""
    pit = scannorm.measure_cell_pitch(dec)
    norm = scannorm.normalize_to_canonical(dec, pit.pitch_px, cell_dots)
    mask = np.ones(norm.img.shape, bool)     # all-True: crop is all piece
    hard, mcell, _llr = segment.piece_cell_bits(
        norm.img, mask, int(round(norm.cell_px_est)))
    if hard.size == 0:
        raise RuntimeError("piece_cell_bits returned empty grid")
    return hard, mcell, float(pit.pitch_px), float(norm.cell_px_est)


def gt_agreement(gt: np.ndarray, bits: np.ndarray, mcell: np.ndarray,
                 rot_k: int, oy: int, ox: int) -> float:
    """Fraction of placed (masked) cells agreeing with the composed page."""
    bk = np.rot90(bits, rot_k)
    mk = np.rot90(mcell, rot_k)
    H, W = gt.shape
    hh = min(bk.shape[0], H - oy)
    ww = min(bk.shape[1], W - ox)
    if hh <= 0 or ww <= 0:
        return 0.0
    sel = mk[:hh, :ww]
    if not sel.any():
        return 0.0
    return float((bk[:hh, :ww][sel] == gt[oy:oy + hh, ox:ox + ww][sel]
                  ).mean())


def main() -> int:
    t_start = time.time()
    spec = FMT.spec()
    cd = int(spec.cell_dots)
    H_cells, W_cells = spec.page_cells_yx
    nty = -(-H_cells // TILE)
    ntx = -(-W_cells // TILE)
    n_tiles = len(ldpc.tile_grid(spec.page_cells_yx))
    assert n_tiles == nty * ntx

    print(f"source sha256 (computing) ...", flush=True)
    h = hashlib.sha256()
    with open(SCAN, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    src_sha = h.hexdigest()
    print(f"  {src_sha}", flush=True)

    arr = tifffile.TiffFile(str(SCAN)).pages[0].asarray(out="memmap")
    y0f, y1f, x0f, x1f = gcs.field_bbox(arr)
    print(f"field bbox @4800: rows {y0f}..{y1f} cols {x0f}..{x1f}", flush=True)

    # ---- ground truth: the composed page cell grid (for agreement audit) --
    print("composing GT page (fountain -> LDPC -> compose) ...", flush=True)
    vspec = gen_e016.make_vspec()
    data = gen_e016.make_data(vspec)
    framed = fountain.encode_volume_pages(data, vspec)[0]
    gt = compose.compose_page(framed["payload_bits"], spec, SEED,
                              page=0).cell_values

    # ---- calibration fit (D2): source px -> page cell, per axis ----------
    # x extent from the bbox is polluted (right-edge artifact); use the
    # NOMINAL field extent (cells * 16 px) to seat the calibration crops,
    # then trust only the fitted mapping afterwards.
    ext_y_nom = H_cells * 8 * cd
    ext_x_nom = W_cells * 8 * cd
    n_cal = int(CAL_MM * MM_SRC)
    cal_pts = []
    for fy, fx in CAL_FRACS:
        sy0 = y0f + int(fy * (ext_y_nom - n_cal))
        sx0 = x0f + int(fx * (ext_x_nom - n_cal))
        dec = crop_decimated(arr, sy0, sx0, n_cal)
        bits, mcell, pitch, cell_px = detect(dec, cd)
        pl = place.place_fragment(bits, spec, SEED, mask=mcell)  # frozen gates
        agree = (gt_agreement(gt, bits, mcell, pl.rot_k, *pl.origin_yx)
                 if pl.origin_yx else 0.0)
        print(f"  cal ({fy},{fx}): ok={pl.ok} rot={pl.rot_k} "
              f"origin={pl.origin_yx} mism={pl.mismatch:.3f} "
              f"rival={pl.rival_mismatch:.3f} agree={agree:.3f}", flush=True)
        if not (pl.ok and pl.rot_k == 0 and agree >= AGREE_MIN):
            print("CALIBRATION FAILED — aborting (no mapping, no sweep)")
            return 1
        cal_pts.append((sy0, sx0, pl.origin_yx[0], pl.origin_yx[1], agree,
                        pl.mismatch))
    # affine fit (skew-aware): cell = A @ [px_y, px_x, 1]
    P = np.array([[p[0], p[1], 1.0] for p in cal_pts])
    oy = np.array([p[2] for p in cal_pts], float)
    ox = np.array([p[3] for p in cal_pts], float)
    coef_y, *_ = np.linalg.lstsq(P, oy, rcond=None)
    coef_x, *_ = np.linalg.lstsq(P, ox, rcond=None)
    res_y = float(np.abs(P @ coef_y - oy).max())
    res_x = float(np.abs(P @ coef_x - ox).max())

    def to_cell(sy0: float, sx0: float) -> tuple[float, float]:
        v = np.array([sy0, sx0, 1.0])
        return float(v @ coef_y), float(v @ coef_x)

    skew_deg = float(np.degrees(np.arctan2(coef_x[0], coef_x[1])))
    print(f"  affine fit: coef_y={np.round(coef_y, 6).tolist()} "
          f"coef_x={np.round(coef_x, 6).tolist()} "
          f"(res y {res_y:.2f} / x {res_x:.2f} cells, skew {skew_deg:.3f} deg)",
          flush=True)
    if max(res_y, res_x) > 2.0:
        print("CALIBRATION RESIDUAL > 2 cells — aborting")
        return 1
    # fitted field bounds in source px along the page center lines
    cyc = y0f + ext_y_nom / 2
    cxc = x0f + ext_x_nom / 2
    fy0 = (0 - coef_y[2] - coef_y[1] * cxc) / coef_y[0]
    fy1 = (H_cells - coef_y[2] - coef_y[1] * cxc) / coef_y[0]
    fx0 = (0 - coef_x[2] - coef_x[0] * cyc) / coef_x[1]
    fx1 = (W_cells - coef_x[2] - coef_x[0] * cyc) / coef_x[1]
    H_mm = (fy1 - fy0) / MM_SRC
    W_mm = (fx1 - fx0) / MM_SRC
    print(f"  fitted field: {H_mm:.1f} x {W_mm:.1f} mm", flush=True)

    # ---- seeded draws, fixed order (detection-independent) ---------------
    gen = rng(SEED, RNG_LABEL)
    positions: dict[int, list[tuple[int, int]]] = {}
    for s in SIZES_MM:                       # 1) positions for all sizes
        lo_y, hi_y = RIM_MM, H_mm - RIM_MM - s
        lo_x, hi_x = RIM_MM, W_mm - RIM_MM - s
        pos = []
        for _ in range(N_POS):
            y_mm = int(gen.integers(int(lo_y), int(hi_y) + 1))
            x_mm = int(gen.integers(int(lo_x), int(hi_x) + 1))
            pos.append((y_mm, x_mm))
        positions[s] = pos
    subsets: dict[tuple[int, int, float], np.ndarray] = {}
    own_rects: dict[tuple[int, int], tuple] = {}
    for s in SIZES_MM:                       # 2) per-trial pending subsets
        n_px = int(s * MM_SRC)
        for i, (y_mm, x_mm) in enumerate(positions[s]):
            sy0 = int(round(fy0 + y_mm * MM_SRC))
            sx0 = int(round(fx0 + x_mm * MM_SRC))
            ey0, ex0 = to_cell(sy0, sx0)     # GT cell rect (truth pending)
            ey1, ex1 = to_cell(sy0 + n_px, sx0 + n_px)
            ty_r = range(max(0, int(ey0) // TILE),
                         min(nty - 1, int(np.ceil(ey1) - 1) // TILE) + 1)
            tx_r = range(max(0, int(ex0) // TILE),
                         min(ntx - 1, int(np.ceil(ex1) - 1) // TILE) + 1)
            own = {ty * ntx + tx for ty in ty_r for tx in tx_r}
            own_rects[(s, i)] = (sy0, sx0, ey0, ex0, sorted(own))
            others = np.array(sorted(set(range(n_tiles)) - own), np.int64)
            for f in FRACTIONS:
                k = int(round(f * others.size))
                subsets[(s, i, f)] = others[gen.permutation(others.size)[:k]]

    # ---- the sweep --------------------------------------------------------
    rows = []
    pieces = []
    critical = []
    for s in SIZES_MM:
        n_px = int(s * MM_SRC)
        for i in range(N_POS):
            y_mm, x_mm = positions[s][i]
            sy0, sx0, ey0, ex0, own = own_rects[(s, i)]
            t0 = time.perf_counter()
            det_ok, det_err = True, None
            try:
                dec = crop_decimated(arr, sy0, sx0, n_px)
                bits, mcell, pitch, cell_px = detect(dec, cd)
            except Exception as e:           # scannorm refusal etc.
                det_ok, det_err = False, f"{type(e).__name__}: {e}"
                bits = mcell = None
                pitch = cell_px = None
            det_s = time.perf_counter() - t0
            pieces.append({"size_mm": s, "pos": i, "y_mm": y_mm,
                           "x_mm": x_mm, "src_yx_4800": [sy0, sx0],
                           "n_px_4800": n_px,
                           "expected_cell_yx": [round(ey0, 2),
                                                round(ex0, 2)],
                           "own_tiles": own, "det_ok": det_ok,
                           "det_err": det_err, "pitch_px": pitch,
                           "cell_px": cell_px, "det_s": round(det_s, 3)})
            for f in FRACTIONS:
                sub = subsets[(s, i, f)]
                n_pending = len(own) + sub.size
                row = {"size_mm": s, "pos": i, "fraction": f,
                       "n_pending_tiles": n_pending}
                if not det_ok:
                    row.update({"admitted": False, "det_fail": True})
                    rows.append(row)
                    continue
                pm = np.zeros((H_cells, W_cells), bool)
                for t in list(own) + list(sub):
                    ty, tx = divmod(int(t), ntx)
                    pm[ty * TILE:(ty + 1) * TILE,
                       tx * TILE:(tx + 1) * TILE] = True
                t0 = time.perf_counter()
                pl = place.place_fragment(bits, spec, SEED, mask=mcell,
                                          pending_cell_mask={0: pm},
                                          gate_true=GATE_TRUE,
                                          gate_decoy=GATE_DECOY)
                place_s = time.perf_counter() - t0
                gap = pl.rival_mismatch - pl.mismatch
                admitted = bool(pl.ok and gap >= GAP_MIN)
                coord_ok = agree = None
                correct = None
                if pl.origin_yx is not None:
                    dy = pl.origin_yx[0] - ey0
                    dx = pl.origin_yx[1] - ex0
                    coord_ok = bool(pl.rot_k == 0 and abs(dy) <= TOL_CELLS
                                    and abs(dx) <= TOL_CELLS)
                    agree = gt_agreement(gt, bits, mcell, pl.rot_k,
                                         *pl.origin_yx)
                    correct = coord_ok
                    if coord_ok != (agree >= AGREE_MIN):
                        row["indicator_conflict"] = True
                row.update({
                    "admitted": admitted, "gate_ok": bool(pl.ok),
                    "gap": round(gap, 4),
                    "mismatch": round(pl.mismatch, 4),
                    "rival_mismatch": round(pl.rival_mismatch, 4),
                    "rot_k": pl.rot_k,
                    "origin_yx": list(pl.origin_yx) if pl.origin_yx else None,
                    "coord_ok": coord_ok,
                    "gt_agreement": round(agree, 4) if agree is not None
                    else None,
                    "correct": correct,
                    "false_placement": bool(admitted and not correct),
                    "support": pl.support,
                    "place_s": round(place_s, 3)})
                rows.append(row)
                if row["false_placement"]:
                    critical.append(row)
                    print(f"  *** CRITICAL: admitted-but-WRONG placement "
                          f"{s}mm pos{i} f={f}: origin={pl.origin_yx} "
                          f"expected=({ey0:.1f},{ex0:.1f}) rot={pl.rot_k} "
                          f"agree={agree}", flush=True)
        done = [r for r in rows if r["size_mm"] == s]
        adm = sum(r["admitted"] for r in done)
        print(f"size {s} mm done: {adm}/{len(done)} admissions across "
              f"fractions, elapsed {time.time() - t_start:.0f}s", flush=True)

    # ---- aggregates -------------------------------------------------------
    aggregates = {}
    for s in SIZES_MM:
        aggregates[str(s)] = {}
        for f in FRACTIONS:
            cell = [r for r in rows
                    if r["size_mm"] == s and r["fraction"] == f]
            ok = [r for r in cell if not r.get("det_fail")]
            adm = [r for r in ok if r["admitted"]]
            fp = [r for r in ok if r.get("false_placement")]
            aggregates[str(s)][f"{f:.2f}"] = {
                "n": len(cell), "det_fail": len(cell) - len(ok),
                "admitted": len(adm),
                "admission_rate": round(len(adm) / len(cell), 3),
                "false_placements": len(fp),
                "usable": bool(len(adm) > 0 and len(fp) == 0),
                "mean_n_pending": round(float(np.mean(
                    [r["n_pending_tiles"] for r in cell])), 1),
                "mean_mismatch": round(float(np.mean(
                    [r["mismatch"] for r in ok])), 4) if ok else None,
                "mean_rival": round(float(np.mean(
                    [r["rival_mismatch"] for r in ok])), 4) if ok else None,
                "mean_gap": round(float(np.mean(
                    [r["gap"] for r in ok])), 4) if ok else None,
                "mean_place_s": round(float(np.mean(
                    [r["place_s"] for r in ok])), 3) if ok else None,
            }

    out = {
        "probe": "p3_grain_pruned (P3 item 2: session-state grain)",
        "date": "2026-07-10",
        "rng": {"seed": SEED.decode(), "label": RNG_LABEL.decode()},
        "design": {"sizes_mm": list(SIZES_MM),
                   "fractions": list(FRACTIONS), "n_pos": N_POS,
                   "rim_mm": RIM_MM, "rotation": "none (014.3 comparability)",
                   "gate": {"gate_true": GATE_TRUE, "gate_decoy": GATE_DECOY,
                            "gap_min": GAP_MIN},
                   "correctness": {"tol_cells": TOL_CELLS,
                                   "agree_min": AGREE_MIN,
                                   "primary": "coord vs source rect (fit)",
                                   "audit": "GT-bit agreement"}},
        "deviations": [
            "D1: detection = session piece path (measure_cell_pitch -> "
            "normalize_to_canonical -> piece_cell_bits), not raw-crop "
            "piece_cell_bits — raw crop carries the Canon +0.4% scale, a "
            "footing artifact (25mm mismatch 0.287 raw vs ~0.12 normalized); "
            "the session a real piece rides normalizes first",
            "D2: field_bbox x1 hits a scan right-edge dark artifact (205mm "
            "vs true 188mm field); sampling extent + expected origins from "
            "a 5-point 12mm calibration placement AFFINE fit (glass skew "
            "~0.23 deg measured; per-axis linear was 4.5 cells off; "
            "residual gate <= 2 cells)"],
        "source_scan": str(SCAN.relative_to(ROOT)),
        "source_sha256": src_sha,
        "field_bbox_4800": [int(y0f), int(y1f), int(x0f), int(x1f)],
        "calibration": {
            "crop_mm": CAL_MM, "fracs": [list(c) for c in CAL_FRACS],
            "points_px_to_cell": [[int(p[0]), int(p[1]), int(p[2]),
                                   int(p[3])] for p in cal_pts],
            "cal_mismatch": [round(p[5], 4) for p in cal_pts],
            "cal_gt_agreement": [round(p[4], 4) for p in cal_pts],
            "affine_coef_y": coef_y.tolist(),
            "affine_coef_x": coef_x.tolist(),
            "skew_deg": round(skew_deg, 4),
            "residual_cells": [round(res_y, 3), round(res_x, 3)],
            "fitted_field_mm": [round(H_mm, 2), round(W_mm, 2)]},
        "tile_grid": [nty, ntx], "n_tiles": n_tiles,
        "pieces": pieces,
        "rows": rows,
        "aggregates": aggregates,
        "critical_false_placements": critical,
        "runtime_s": round(time.time() - t_start, 1),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {OUT.relative_to(ROOT)} "
          f"({time.time() - t_start:.0f}s total)")

    # ---- console table ----------------------------------------------------
    hdr = "size | " + " | ".join(f"f={f:.2f}" for f in FRACTIONS)
    print("\nadmission rate (n admitted / n trials; * = false placements!)")
    print(hdr)
    for s in SIZES_MM:
        cells = []
        for f in FRACTIONS:
            a = aggregates[str(s)][f"{f:.2f}"]
            mark = "*" if a["false_placements"] else ""
            cells.append(f"{a['admitted']}/{a['n']}{mark}")
        print(f"{s:4d} | " + " | ".join(f"{c:>6s}" for c in cells))
    print(f"\nfalse placements TOTAL: {len(critical)} (must be zero)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

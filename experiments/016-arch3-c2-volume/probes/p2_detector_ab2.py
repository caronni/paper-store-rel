#!/usr/bin/env python
"""P2 detector A/B, iteration 2: the ring + supervised-refinement chain.

Round-1 findings (probes/p2_detector_ab.py, build/p2_detector_ab.json,
N=219) + the P3.1 rotation curve + a direct 5-piece verification measured
the real-toner "13-14% BER binder" as a SUM of separable terms:
  ring     +3-4pp   grow-out mask cells sampling white backing (~9% of
                    sites, ~coin-flip wrong) — verified full-vs-core on 5
                    placed pieces (e.g. 0.133->0.106);
  angle    +0..20pp lattice_angle error ~0.4-0.5deg median where <0.15deg
                    is free (P3.1 dose-response; the resample itself is
                    measured FREE at genie angle);
  recal    -0.3..1pp per-piece QDA on placed pilot labels (round 1: B-A).
This probe measures the composed production-candidate chain:

  ARM A  unchanged baseline (reference continuity with 016.4 / round 1).
  ARM E  A's detection + CORE-mask placement/scoring (erode 4 cells):
         isolates the ring lever on the production detector.
  ARM F  the full chain, self-consistent rot-free geometry:
         rot-free detect at the segmenter angle (integer-phase search) ->
         core-mask place -> if admitted, PILOT-SUPERVISED refinement of
         (angle +-0.6deg step 0.05, CONTINUOUS sub-cell phase +-0.5 step
         0.125 cells) minimizing mismatch against the placed pilot
         reference on a TRAIN half of sites (held-out half reported;
         payload GT-BER is out-of-sample by construction) -> full
         re-sample (order-3) -> core-label QDA recal -> calibrated LLRs.

Pre-registered metrics: admissions (gap gate), 0 wrong placements
(gt-agreement audit), core mismatch held-out pre/post refine, core GT-BER
per arm, full-mask GT-BER (continuity), angle moved by refinement.

Usage (from experiments/016-arch3-c2-volume/):
  ../../env/bin/python probes/p2_detector_ab2.py [--limit N]
      [--out build/p2_detector_ab2.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from paperholo import compose, place, scannorm, segment  # noqa: E402
import gen_e016  # noqa: E402
import p2_detector_ab as r1  # noqa: E402  (round-1 machinery, reused)

Image.MAX_IMAGE_PIXELS = None
SEED = gen_e016.SEED
DPI = 2400.0
PX_MM = DPI / 25.4
ERODE_CELLS = 4              # ring depth: grow-out ~3 cells + 1 safety
REFINE_ANG = np.arange(-0.6, 0.6 + 1e-9, 0.05)
REFINE_PH = np.arange(-0.5, 0.5 + 1e-9, 0.125)


def core(kmask: np.ndarray) -> np.ndarray:
    e = ndimage.binary_erosion(kmask, iterations=ERODE_CELLS)
    return e if e.any() else kmask          # tiny piece: keep full


def piece_sites(pl: place.Placement, grid_shape: tuple, vals: np.ndarray,
                smask: np.ndarray, kmask: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray]:
    """Pilot sites inside the placed piece: (piece-frame (i,j) int array,
    site values). Piece-frame = the detected grid BEFORE the placement
    rot90 (invert rot_k on the page window)."""
    oy, ox = pl.origin_yx
    kr = np.rot90(kmask, pl.rot_k)
    H, W = vals.shape
    hh, ww = min(kr.shape[0], H - oy), min(kr.shape[1], W - ox)
    sel = smask[oy:oy + hh, ox:ox + ww] & kr[:hh, :ww]
    ys, xs = np.nonzero(sel)
    v = vals[oy:oy + hh, ox:ox + ww][sel]
    # map rotated-window coords back to piece-frame indices
    full = np.zeros(kr.shape, bool)
    full[ys, xs] = True
    back = np.rot90(full, -pl.rot_k)
    iy, ix = np.nonzero(back)
    # values must be reordered identically: rotate an index image back
    vi = np.full(kr.shape, -1, np.int64)
    vi[ys, xs] = np.arange(ys.size)
    vb = np.rot90(vi, -pl.rot_k)
    order = vb[iy, ix]
    return np.stack([iy, ix], 1), v[order]


def supervised_refine(glass: np.ndarray, gmask: np.ndarray, backing: float,
                      angle0: float, p: float, dy: int, dx: int,
                      sites_ij: np.ndarray, site_vals: np.ndarray
                      ) -> tuple[float, float, float, dict]:
    """(angle, dy_f, dx_f) minimizing TRAIN-half pilot mismatch; returns
    held-out mismatch before/after in meta. Sites sampled at one center
    point per candidate (order-1) — the search statistic; the final
    re-sample is order-3 area sampling."""
    im = np.where(gmask, np.asarray(glass, np.float32), np.float32(backing))
    mid = float(np.median(im[gmask])) if gmask.any() else 128.0
    tr = np.arange(sites_ij.shape[0]) % 2 == 0
    ho = ~tr

    def eval_cand(ang, py, px):
        M, off, _ = r1._rotate_transform(im.shape, ang)
        yc = dy + py * p + (sites_ij[:, 0] + 0.5) * p
        xc = dx + px * p + (sites_ij[:, 1] + 0.5) * p
        coords = M @ np.stack([yc, xc]) + off[:, None]
        m = ndimage.map_coordinates(im, coords, order=1, cval=backing)
        bits = (m < mid)
        return (float(np.mean(bits[tr] != (site_vals[tr] > 0))),
                float(np.mean(bits[ho] != (site_vals[ho] > 0))))

    _, base_ho = eval_cand(angle0, 0.0, 0.0)   # the unrefined reference
    best = None
    for da in REFINE_ANG:
        M, off, _ = r1._rotate_transform(im.shape, angle0 + da)
        for py in REFINE_PH:
            for px in REFINE_PH:
                yc = dy + py * p + (sites_ij[:, 0] + 0.5) * p
                xc = dx + px * p + (sites_ij[:, 1] + 0.5) * p
                coords = M @ np.stack([yc, xc]) + off[:, None]
                m = ndimage.map_coordinates(im, coords, order=1,
                                            cval=backing)
                bits = (m < mid)
                mis_tr = float(np.mean(bits[tr] != (site_vals[tr] > 0)))
                if best is None or mis_tr < best[0]:
                    mis_ho = float(np.mean(bits[ho] != (site_vals[ho] > 0)))
                    best = (mis_tr, angle0 + da, py * p, px * p, mis_ho)
    mis_tr, ang, oy_f, ox_f, mis_ho = best
    return ang, dy + oy_f, dx + ox_f, {
        "heldout_pre": base_ho, "heldout_post": mis_ho,
        "angle_moved": ang - angle0}


def resample_at(glass, gmask, backing, ang, dyf, dxf, p, n_sub=3):
    """Full-grid order-3 area sampling at a refined (angle, float phase)."""
    im = np.where(gmask, np.asarray(glass, np.float32), np.float32(backing))
    mk = np.asarray(gmask, np.float32)
    mid = float(np.median(im[gmask])) if gmask.any() else 128.0
    M, off, out_shape = r1._rotate_transform(im.shape, ang)
    n_cy = int((out_shape[0] - dyf) // p)
    n_cx = int((out_shape[1] - dxf) // p)
    if n_cy < 2 or n_cx < 2:
        return None
    ycs = dyf + np.arange(n_cy) * p
    xcs = dxf + np.arange(n_cx) * p
    offs = (np.arange(n_sub) + 0.5) / n_sub * p
    means = np.zeros((n_cy, n_cx), np.float64)
    cover = np.zeros((n_cy, n_cx), np.float64)
    imf = ndimage.spline_filter(im, order=3)
    for dv in offs:
        for du in offs:
            oy, ox = np.meshgrid(ycs + dv, xcs + du, indexing="ij")
            coords = M @ np.array([oy.ravel(), ox.ravel()]) + off[:, None]
            means += ndimage.map_coordinates(
                imf, coords, order=3, prefilter=False,
                cval=backing).reshape(n_cy, n_cx)
            cover += ndimage.map_coordinates(
                mk, coords, order=1, cval=0.0).reshape(n_cy, n_cx)
    means /= n_sub * n_sub
    kmask = (cover / (n_sub * n_sub)) > 0.85
    if not kmask.any():
        return None
    spread = float(np.abs(means[kmask] - mid).mean()) if kmask.any() else 1.0
    llr = np.clip((mid - means) / max(spread, 1e-6), -8.0, 8.0) * 2.0
    hard = (means < mid).astype(np.uint8)
    return hard, kmask, llr, means, mid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", type=Path,
                    default=ROOT / "scratch/confetti_session_white")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parents[1]
                    / "build/p2_detector_ab2.json")
    args = ap.parse_args()

    r1._selftest_rotate_transform()
    spec = gen_e016.make_spec()
    vals, smask = place.pilot_field(spec, SEED, 0)
    manifest = json.loads((args.fixture / "session_manifest.json"
                           ).read_text())
    pend = {0: np.ones(tuple(spec.page_cells_yx), bool)}
    rows = []
    t0 = time.time()
    for scan in manifest["scans"]:
        img = np.asarray(Image.open(args.fixture / f"{scan['scan']}.png"
                                    ).convert("L"), np.float32)
        pieces = segment.segment_pieces(img, cell_px=8.0, dpi=DPI)
        backing = segment.estimate_backing(img)
        n_seen = 0
        for p in pieces:
            if max(p.bbox_glass[2], p.bbox_glass[3]) / PX_MM \
                    >= r1.SUB_GRAIN_MAX_MM:
                continue
            ent = r1._match_manifest(p, scan["manifest"])
            if ent is None:
                continue
            if args.limit and n_seen >= args.limit:
                break
            n_seen += 1
            row = {"scan": scan["scan"], "side_mm": ent["side_mm"],
                   "angle_deg": ent["angle_deg"]}

            # ---- ARM A + E (same detection, full vs core placement mask)
            got = r1.arm_a_bits(p)
            if got is not None:
                hard, km, llr, means = got
                pla = place.place_fragment(
                    hard, spec, SEED, mask=km, pending_cell_mask=pend,
                    gate_true=r1.GATE_TRUE, gate_decoy=r1.GATE_DECOY)
                row["A"] = _sc(pla, hard, km)
                kc = core(km)
                ple = place.place_fragment(
                    hard, spec, SEED, mask=kc, pending_cell_mask=pend,
                    gate_true=r1.GATE_TRUE, gate_decoy=r1.GATE_DECOY)
                row["E"] = _sc(ple, hard, kc)

            # ---- ARM F (rot-free chain, core mask, supervised refine)
            y0, x0, h, w = p.bbox_glass
            glass = img[y0:y0 + h, x0:x0 + w]
            gm = r1._glass_mask(p, glass.shape)
            try:
                pit = float(scannorm.measure_cell_pitch(p.img).pitch_px)
            except Exception:
                pit = 8.0
            try:
                im0 = np.where(gm, np.asarray(glass, np.float32),
                               np.float32(backing))
                mid0 = float(np.median(im0[gm]))
                M0, off0, os0 = r1._rotate_transform(im0.shape, p.angle_deg)
                ph = r1._phase_scan(im0, gm.astype(np.float32), mid0,
                                    backing, M0, off0, os0, pit)
            except Exception:
                ph = None
            if ph is not None:
                _, dy0, dx0 = ph
                got_f = resample_at(glass, gm, backing, p.angle_deg,
                                    dy0, dx0, pit)
                if got_f is not None:
                    hf, kf, lf, mf, midf = got_f
                    kfc = core(kf)
                    plf = place.place_fragment(
                        hf, spec, SEED, mask=kfc, pending_cell_mask=pend,
                        gate_true=r1.GATE_TRUE, gate_decoy=r1.GATE_DECOY)
                    fr = _sc(plf, hf, kfc)
                    if r1.gate(plf):
                        sij, sv = piece_sites(plf, hf.shape, vals, smask,
                                              kfc)
                        if sij.shape[0] >= 60:
                            ang, dyf, dxf, meta = supervised_refine(
                                glass, gm, backing, p.angle_deg, pit,
                                dy0, dx0, sij, sv)
                            got_r = resample_at(glass, gm, backing, ang,
                                                dyf, dxf, pit)
                            if got_r is not None:
                                hr, kr_, lr, mr, midr = got_r
                                krc = core(kr_)
                                rec = r1.qda_recal(mr, krc, plf, spec,
                                                   SEED)
                                fr["refine"] = meta
                                fr["_bk2"] = ((hr if rec is None
                                               else rec[0]), krc, plf)
                                fr["recal"] = rec is not None
                    row["F"] = fr
            rows.append(row)

    # ---- GT audit
    import paperholo.fountain as fountain
    vspec = gen_e016.make_vspec()
    framed = fountain.encode_volume_pages(gen_e016.make_data(vspec),
                                          vspec)[0]
    gt_cells = compose.compose_page(framed["payload_bits"], spec, SEED,
                                    page=0).cell_values
    for row in rows:
        for arm in ("A", "E", "F"):
            if arm not in row:
                continue
            r = row[arm]
            if r.get("_bk") is not None:
                bits, kmk, pl = r.pop("_bk")
                if r["placed_ok"]:
                    b = r1.gt_ber(bits, kmk, pl, gt_cells)
                    r["gt_ber"] = b
                    r["placement_correct"] = (
                        b is not None and b < r1.WRONG_PLACEMENT_BER)
                    bc = r1.gt_ber(bits, core(kmk), pl, gt_cells)
                    r["gt_ber_core"] = bc
            r.pop("_bk", None)
            if r.get("_bk2") is not None:
                bits, kmk, pl = r.pop("_bk2")
                r["gt_ber_refined_core"] = r1.gt_ber(bits, kmk, pl,
                                                     gt_cells)
            r.pop("_bk2", None)

    out = {"fixture": str(args.fixture), "n_pieces": len(rows),
           "erode_cells": ERODE_CELLS,
           "elapsed_s": round(time.time() - t0, 1), "rows": rows,
           "summary": _summarize(rows)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out["summary"], indent=1, default=float))
    print(f"-> {args.out}")
    return 0


def _sc(pl, bits, kmask):
    ok = r1.gate(pl)
    return {"mismatch": pl.mismatch, "rival": pl.rival_mismatch,
            "gap": pl.rival_mismatch - pl.mismatch, "placed_ok": ok,
            "placement_correct": None, "_bk": (bits, kmask, pl)}


def _summarize(rows: list) -> dict:
    def med(v):
        v = [x for x in v if x is not None]
        return float(np.median(v)) if v else None
    s: dict = {}
    small = [x for x in rows if x["side_mm"] <= 16]
    for arm in ("A", "E", "F"):
        r = [x[arm] for x in small if arm in x]
        if not r:
            continue
        adm = [x for x in r if x["placed_ok"]]
        okp = [x for x in adm if x.get("placement_correct")]
        s[arm] = {
            "n": len(r), "mismatch_median": med([x["mismatch"] for x in r]),
            "admitted": len(adm),
            "admitted_wrong": sum(1 for x in adm
                                  if x.get("placement_correct") is False),
            "gt_ber_full": med([x["gt_ber"] for x in okp
                                if x.get("gt_ber") is not None]),
            "gt_ber_core": med([x["gt_ber_core"] for x in okp
                                if x.get("gt_ber_core") is not None]),
        }
        if arm == "F":
            ref = [x for x in okp if "refine" in x]
            s[arm]["refined_n"] = len(ref)
            s[arm]["heldout_pre"] = med([x["refine"]["heldout_pre"]
                                         for x in ref])
            s[arm]["heldout_post"] = med([x["refine"]["heldout_post"]
                                          for x in ref])
            s[arm]["angle_moved_absmed"] = med(
                [abs(x["refine"]["angle_moved"]) for x in ref])
            s[arm]["gt_ber_refined_core"] = med(
                [x["gt_ber_refined_core"] for x in ref
                 if x.get("gt_ber_refined_core") is not None])
    return s


if __name__ == "__main__":
    sys.exit(main())

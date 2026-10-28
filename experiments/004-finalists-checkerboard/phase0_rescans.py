"""Phase 0: multi-scan / mode / rotation analysis of the E004 sheet (004.0b).

Five scans of the SAME print (same sheet, 2026-07-05 evening):
  1col  flat 0°, color        1bw   flat 0°, GREY — placement identical to 1col
  2col  flat 0°, displaced    3col90  rotated 90° (top part of sheet only)
  4col180  rotated 180°

Measures, all at genie warp (scan-side levers, same footing as 004.0):
  (a) scan-MODE transport test: is 'bw' just a channel transform of the
      color acquisition? Same placement => if yes, the affine y-scale AND
      the stochastic transport-step catalog must match 1col exactly.
  (b) grey-vs-color delta on B1/B2 (per-tile, paired).
  (c) rotation deltas (90° on covered tiles; 180° full).
  (d) MULTI-SCAN COMBINING: B1 by summing per-scan blind context LLRs;
      B2 by averaging MAD-normalized residual fields. Gain curve vs N.
Scans are processed sequentially and freed (300 MB each); only the small
per-tile LLR/residual fields are kept. GT is the scoring instrument.
Writes build/phase0_report.json.
"""
from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy import ndimage

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import analyze_e004 as ae  # noqa: E402
import analyze_k4e2_context as k4  # noqa: E402
import analyze_modprobe as amp  # noqa: E402
import cal_core as cc  # noqa: E402

BUILD = _HERE / "build"
SCANS_DIR = _HERE.parents[1] / "scans"
SCANS = {
    "1col": "finalists-1-col.png",
    "1bw": "finalists-1-bw.png",
    "2col": "finalists-2-col.png",
    "3col90": "finalists-3-col.png",
    "4col180": "finalists-4-col.png",
}
CELLS_MM2_C2 = (600 / 25.4 / 2) ** 2
DOTS_MM2 = (600 / 25.4) ** 2


def tile_in_scan(scan: dict, e: dict, shape) -> bool:
    coef = np.asarray(scan["affine"], np.float64)
    cs = np.array([[e["x_dots"], e["y_dots"]],
                   [e["x_dots"] + e["w_dots"], e["y_dots"]],
                   [e["x_dots"], e["y_dots"] + e["h_dots"]],
                   [e["x_dots"] + e["w_dots"], e["y_dots"] + e["h_dots"]]])
    sx = coef[0] * cs[:, 0] + coef[1] * cs[:, 1] + coef[2]
    sy = coef[3] * cs[:, 0] + coef[4] * cs[:, 1] + coef[5]
    return bool(sx.min() >= 2 and sy.min() >= 2
                and sx.max() < shape[1] - 2 and sy.max() < shape[0] - 2)


def process_scan(tag: str, manifest: dict) -> dict:
    path = SCANS_DIR / SCANS[tag]
    out: dict = {"tag": tag, "file": SCANS[tag]}
    scan = cc.load_scan(path, compute_sha256=False)
    try:
        reg = cc.register(scan, manifest)
    except Exception as exc:
        out["registered"] = False
        out["error"] = repr(exc)
        print(f"[{tag}] REGISTRATION FAILED: {exc!r}", flush=True)
        return out
    coef = np.asarray(scan["affine"], np.float64)
    out["registered"] = True
    out["reg"] = {k: v for k, v in reg.items()
                  if isinstance(v, (int, float, str, bool))}
    shape = scan["arr"].shape[:2] if "arr" in scan else None

    # transport-step catalog on one tall B1 tile (mode test needs it)
    e14 = cc.entry(scan["manifest"], "T14/B1")
    gt14 = cc.load_gt(e14)
    arr = cc._channel_f32(scan, "grey")
    shape = arr.shape
    sq = {"name": "modetest", "x_dots": e14["x_dots"], "y_dots": e14["y_dots"],
          "w_dots": e14["w_dots"], "h_dots": e14["w_dots"]}
    import scanlab
    dd = scanlab.decode_cells(arr, scan["affine"], sq,
                              gt14[:e14["w_dots"]].astype(np.uint8), 2,
                              soft=False, diagnostics=True)
    out["steps_T14top"] = [(round(float(y), 1), round(float(m), 3))
                           for y, m in dd.get("steps", [])]

    b1, b2 = {}, {}
    for t in manifest["tiles"]:
        if t["class"] not in ("B1", "B2"):
            continue
        e = cc.entry(scan["manifest"], t["name"])
        if not tile_in_scan(scan, e, shape):
            continue
        gt = cc.load_gt(e)
        if t["class"] == "B1":
            r = ae.decode_rect_by_squares(scan, e, gt, 2, "grey")
            gtc = gt[::2, ::2].astype(bool)
            llr = np.asarray(r["llr_ctx"], np.float64)
            b1[t["name"]] = {
                "llr": llr.astype(np.float32),
                "ber_hard": float(r["err_map"].mean()),
                "ber_ctx": float(((llr > 0) != gtc).mean()),
            }
        else:
            r = ae.decode_rect_by_squares(scan, e, gt, 1, "grey",
                                          soft=False, diagnostics=False)
            m = np.asarray(r["means"], np.float64)
            resid = m - ndimage.median_filter(m, size=31, mode="nearest")
            mad = float(np.median(np.abs(resid - np.median(resid)))) + 1e-9
            p_ink = float(e["params"]["ink_fraction"])
            bits = amp.fixed_rate_bits(m, p_ink)
            b2[t["name"]] = {
                "resid_norm": (resid / mad).astype(np.float32),
                "ber": float((bits.astype(bool) != gt.astype(bool)).mean()),
                "p_ink": p_ink,
            }
    out["b1"] = b1
    out["b2"] = b2
    n1 = [v["ber_ctx"] for v in b1.values()]
    n2 = [v["ber"] for v in b2.values()]
    print(f"[{tag}] reg ok ({out['reg'].get('n_landmarks_used')} lm, "
          f"px/dot {coef[0]:.5f}/{coef[4]:.5f}, "
          f"rot {out['reg'].get('rotation_deg', 0):.2f} deg, "
          f"mirrored {out['reg'].get('mirrored')}): "
          f"B1 tiles {len(b1)} ctx mean {np.mean(n1) if n1 else float('nan'):.4f}, "
          f"B2 tiles {len(b2)} ber mean {np.mean(n2) if n2 else float('nan'):.4f}",
          flush=True)
    scan.clear()
    gc.collect()
    return out


def combine_b1(results: dict, subset: list[str], manifest: dict) -> dict:
    pertile = {}
    for t in manifest["tiles"]:
        if t["class"] != "B1":
            continue
        name = t["name"]
        llrs = [results[s]["b1"][name]["llr"].astype(np.float64)
                for s in subset if results[s].get("registered")
                and name in results[s]["b1"]]
        if not llrs:
            continue
        tot = np.sum(llrs, axis=0)
        e = cc.entry_cache[name] if hasattr(cc, "entry_cache") else None
        gt = np.load(BUILD / f"e004_gt/{name.replace('/', '__')}.npy")
        gtc = gt[::2, ::2].astype(bool)
        err = (tot > 0) != gtc
        # split-half PAVA recal on the combined LLR
        iy, ix = np.mgrid[0:tot.shape[0], 0:tot.shape[1]]
        half = ((iy + ix) % 2).astype(bool)
        mis = []
        for train in (half, ~half):
            cbin, p = k4.fit_monotone_map(np.abs(tot[train]), err[train])
            mis.append(k4.mi_bits(k4.apply_map(tot[~train], cbin, p),
                                  gtc[~train]))
        pertile[name] = {"ber": float(err.mean()), "n_scans": len(llrs),
                         "mi_recal": float(np.mean(mis))}
    bers = [v["ber"] for v in pertile.values()]
    mis = [v["mi_recal"] for v in pertile.values()]
    return {"tiles": len(pertile), "ber_ctx_mean": float(np.mean(bers)),
            "ber_ctx_range": [float(np.min(bers)), float(np.max(bers))],
            "mi_recal_mean": float(np.mean(mis)),
            "b_mm2": float(np.mean(mis)) * CELLS_MM2_C2,
            "per_tile": {k: {kk: vv for kk, vv in v.items()}
                         for k, v in pertile.items()}}


def combine_b2(results: dict, subset: list[str], manifest: dict) -> dict:
    bers, rates = [], []
    for t in manifest["tiles"]:
        if t["class"] != "B2":
            continue
        name = t["name"]
        fields = [results[s]["b2"][name] for s in subset
                  if results[s].get("registered") and name in results[s]["b2"]]
        if not fields:
            continue
        avg = np.mean([f["resid_norm"].astype(np.float64) for f in fields],
                      axis=0)
        p_ink = fields[0]["p_ink"]
        thr = np.quantile(avg, p_ink)
        bits = (avg < thr).astype(np.uint8)
        gt = np.load(BUILD / f"e004_gt/{name.replace('/', '__')}.npy")
        ber = float((bits.astype(bool) != gt.astype(bool)).mean())
        e = next(p for p in manifest["patches"] if p["name"] == name)
        h_src = float(e["params"]["sampler_entropy_bits_per_dot"])
        bers.append(ber)
        rates.append(h_src * (1 - k4.h2(ber)))
    return {"tiles": len(bers), "ber_mean": float(np.mean(bers)),
            "rate_mean_b_per_dot": float(np.mean(rates)),
            "b_mm2": float(np.mean(rates)) * DOTS_MM2}


def main() -> None:
    t0 = time.time()
    manifest = cc.load_manifest(ae.MANIFEST_PATH)
    results = {}
    for tag in SCANS:
        results[tag] = process_scan(tag, manifest)

    report: dict = {"scans": {t: {k: v for k, v in r.items()
                                  if k not in ("b1", "b2")}
                              for t, r in results.items()}}

    # (a) mode test: 1col vs 1bw (same placement)
    if results["1col"].get("registered") and results["1bw"].get("registered"):
        rc, rb = results["1col"]["reg"], results["1bw"]["reg"]
        sc, sb = results["1col"]["steps_T14top"], results["1bw"]["steps_T14top"]
        matched = sum(1 for y, m in sc
                      if any(abs(y - y2) < 6 and abs(m - m2) < 0.3
                             for y2, m2 in sb))
        report["mode_test"] = {
            "px_per_dot_y": [rc.get("px_per_dot_y"), rb.get("px_per_dot_y")],
            "y_scale_delta_pct": 100 * (rb.get("px_per_dot_y", 0)
                                        - rc.get("px_per_dot_y", 0))
            / max(rc.get("px_per_dot_y", 1), 1e-9),
            "steps_1col_T14": sc, "steps_1bw_T14": sb,
            "steps_matched": f"{matched}/{len(sc)}",
            "verdict_hint": "same transport pass iff y-scale delta ~0 AND "
                            "step catalogs match",
        }

    # (b)-(d): per-scan summaries + combining ladders
    singles = {}
    for tag, r in results.items():
        if not r.get("registered") or not r.get("b1"):
            continue
        n1 = [v["ber_ctx"] for v in r["b1"].values()]
        n2 = [v["ber"] for v in r["b2"].values()]
        singles[tag] = {"b1_tiles": len(n1),
                        "b1_ctx_mean": float(np.mean(n1)),
                        "b2_tiles": len(n2), "b2_ber_mean": float(np.mean(n2))}
    report["singles"] = singles

    ladders = [["1col"], ["1col", "2col"], ["1col", "2col", "4col180"],
               ["1col", "2col", "4col180", "1bw"],
               ["1col", "2col", "4col180", "1bw", "3col90"]]
    report["combining_b1"] = {"+".join(s): combine_b1(results, s, manifest)
                              for s in ladders}
    report["combining_b2"] = {"+".join(s): combine_b2(results, s, manifest)
                              for s in ladders}

    # rotated delta on tiles covered by the 90° scan
    if results["3col90"].get("registered") and results["3col90"].get("b1"):
        rot = {}
        for name, v in results["3col90"]["b1"].items():
            base = results["1col"]["b1"].get(name)
            if base:
                rot[name] = {"ctx_90": v["ber_ctx"], "ctx_flat": base["ber_ctx"],
                             "delta_pp": 100 * (v["ber_ctx"] - base["ber_ctx"])}
        report["rot90_b1_delta"] = rot

    # strip bulky fields before writing
    report["runtime_s"] = round(time.time() - t0, 1)
    (BUILD / "phase0_report.json").write_text(json.dumps(report, indent=1))

    print("\n==== PHASE 0 SUMMARY ====", flush=True)
    if "mode_test" in report:
        mt = report["mode_test"]
        print(f"mode test: y-scale delta {mt['y_scale_delta_pct']:+.3f}% | "
              f"steps matched {mt['steps_matched']}")
    for tag, s in singles.items():
        print(f"{tag:8s}: B1 ctx {s['b1_ctx_mean']:.4f} ({s['b1_tiles']}t) | "
              f"B2 {s['b2_ber_mean']:.4f} ({s['b2_tiles']}t)")
    for key in report["combining_b1"]:
        c1, c2n = report["combining_b1"][key], report["combining_b2"][key]
        print(f"COMBINE [{key}]: B1 ctx {c1['ber_ctx_mean']:.4f} recal "
              f"{c1['mi_recal_mean']:.3f} = {c1['b_mm2']:.1f} b/mm2 | "
              f"B2 {c2n['ber_mean']:.4f} -> {c2n['rate_mean_b_per_dot']:.4f} "
              f"b/dot = {c2n['b_mm2']:.1f} b/mm2")
    print(f"runtime {report['runtime_s']}s -> build/phase0_report.json",
          flush=True)


if __name__ == "__main__":
    main()

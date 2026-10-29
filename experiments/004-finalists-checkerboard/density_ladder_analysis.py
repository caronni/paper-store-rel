"""005 density-ladder analysis: D1 / D5 / D3+RET=OFF vs the D3/RET=ON baseline.

Same e004.ps payload on all four sheets; scans all 1200 dpi color. The
by-eye verdict was "no difference" — these are the instruments that decide
whether @PJL SET DENSITY reached the engine on the raw PS path:

  ref-solid density   -log10(K-solid / adjacent paper) from the ref row
  effective coverage  ink fraction of B2 tiles at a blind 2-GMM threshold
                      (construction prior is 0.414-0.416; excess = dot gain)
  B1 closure split    fa(white->ink) vs miss on edge + interior tiles — the
                      white-closure densitometer (day-2's failure mode)
  B2 run dropout      whole-2-run loss rate — the short-feature densitometer

Writes build/density_ladder_report.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy import ndimage

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import analyze_e004 as ae  # noqa: E402
import analyze_modprobe as amp  # noqa: E402
import cal_core as cc  # noqa: E402

BUILD = _HERE / "build"
SCANS_DIR = Path()  # the run's scans (evidence archive), set from --scan-dir
SHEETS = {
    "D3_RETON": "finalists-1-col.png",     # 004.0 print = ladder midpoint
    "D1": "005.1.png",
    "D5": "005.2.png",
    "D3_RETOFF": "005.3.png",
}
B1_TILES = ("T00/B1", "T14/B1", "T70/B1", "T47/B1", "T25/B1", "T53/B1")
B2_TILES = ("T02/B2", "T40/B2", "T15/B2", "T60/B2")


def ref_density(scan: dict) -> dict:
    """K-solid vs adjacent-paper density from the ref row (grey channel)."""
    arr = cc._channel_f32(scan, "grey")
    coef = np.asarray(scan["affine"], np.float64)

    def mean_at(x_mm: float, y_mm: float, w_mm: float, h_mm: float) -> float:
        x0, y0 = round(x_mm / 25.4 * 600), round(y_mm / 25.4 * 600)
        w, h = round(w_mm / 25.4 * 600), round(h_mm / 25.4 * 600)
        yy, xx = np.mgrid[y0:y0 + h:4, x0:x0 + w:4].astype(np.float64)
        sx = coef[0] * xx + coef[1] * yy + coef[2]
        sy = coef[3] * xx + coef[4] * yy + coef[5]
        return float(np.mean(ndimage.map_coordinates(arr, [sy, sx], order=1,
                                                     mode="nearest")))
    # ref_clean_K at (14, 280) 8x4.8mm; paper gap directly right of the
    # cmyk refs (use 110..114, 280..284.8 — the labelled 'paper = gaps')
    k = mean_at(15.0, 280.8, 6.0, 3.2)
    paper = mean_at(50.0, 280.8, 6.0, 3.2)   # gap between clean refs and cmyk refs
    return {"k_solid_grey": k, "paper_grey": paper,
            "density_D": float(-np.log10(max(k, 1.0) / max(paper, 1e-3)))}


def b2_run_dropout(gt: np.ndarray, err: np.ndarray) -> dict:
    stats: dict[int, list] = {}
    for row_g, row_e in zip(gt.astype(int), err):
        d = np.diff(np.concatenate(([0], row_g, [0])))
        starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
        for s, t in zip(starts, ends):
            length = min(t - s, 6)
            n, m, w = stats.get(length, (0, 0.0, 0))
            miss = row_e[s:t].mean()
            stats[length] = (n + 1, m + miss, w + int(miss > 0.5))
    return {str(k): {"n": v[0], "mean_miss": round(v[1] / v[0], 4),
                     "dropout": round(v[2] / v[0], 4)}
            for k, v in sorted(stats.items())}


def process(tag: str, manifest: dict) -> dict:
    scan = cc.load_scan(SCANS_DIR / SHEETS[tag], compute_sha256=False)
    reg = cc.register(scan, manifest)
    out: dict = {"sheet": tag, "file": SHEETS[tag],
                 "landmarks": reg.get("n_landmarks_used")}
    out["ref"] = ref_density(scan)

    b1 = {}
    for name in B1_TILES:
        e = cc.entry(scan["manifest"], name)
        gt = cc.load_gt(e)
        gtc = gt[::2, ::2].astype(bool)
        r = ae.decode_rect_by_squares(scan, e, gt, 2, "grey")
        llr = np.asarray(r["llr_ctx"], np.float64)
        err = (llr > 0) != gtc
        b1[name] = {"ber_hard": float(r["err_map"].mean()),
                    "ber_ctx": float(err.mean()),
                    "fa_white_to_ink": float(err[~gtc].mean()),
                    "miss_ink_to_white": float(err[gtc].mean())}
    out["b1"] = b1

    b2 = {}
    cov = []
    for name in B2_TILES:
        e = cc.entry(scan["manifest"], name)
        gt = cc.load_gt(e)
        r = ae.decode_rect_by_squares(scan, e, gt, 1, "grey",
                                      soft=False, diagnostics=False)
        m = np.asarray(r["means"], np.float64)
        p_ink = float(e["params"]["ink_fraction"])
        bits = amp.fixed_rate_bits(m, p_ink)
        gtb = gt.astype(bool)
        err = bits.astype(bool) != gtb
        # blind coverage: Otsu-ish threshold on the residual field
        resid = m - ndimage.median_filter(m, size=31, mode="nearest")
        thr = 0.5 * (np.quantile(resid, 0.25) + np.quantile(resid, 0.75))
        cov.append(float((resid < thr).mean()))
        b2[name] = {"ber": float(err.mean()),
                    "miss": float(err[gtb].mean()),
                    "fa": float(err[~gtb].mean()),
                    "runs": b2_run_dropout(gt, err)}
    out["b2"] = b2
    out["b2_blind_coverage_mean"] = float(np.mean(cov))

    f = out["ref"]
    print(f"[{tag}] D {f['density_D']:.3f} | blind cov {out['b2_blind_coverage_mean']:.4f} "
          f"(construction ~0.415) | B1 ctx {np.mean([v['ber_ctx'] for v in b1.values()]):.4f} "
          f"fa {np.mean([v['fa_white_to_ink'] for v in b1.values()]):.4f} | "
          f"B2 ber {np.mean([v['ber'] for v in b2.values()]):.4f} "
          f"2run-dropout {np.mean([float(v['runs']['2']['dropout']) for v in b2.values()]):.3f}",
          flush=True)
    scan.clear()
    import gc
    gc.collect()
    return out


def main() -> None:
    t0 = time.time()
    manifest = cc.load_manifest(ae.MANIFEST_PATH)
    report = {tag: process(tag, manifest) for tag in SHEETS}
    report["runtime_s"] = round(time.time() - t0, 1)
    (BUILD / "density_ladder_report.json").write_text(
        json.dumps(report, indent=1))
    print("\n==== DENSITY LADDER ====", flush=True)
    print(f"{'sheet':10s} {'ref D':>6s} {'cov':>7s} {'B1ctx':>7s} {'B1 fa':>7s} "
          f"{'B1miss':>7s} {'B2ber':>7s} {'2run-drop':>9s}")
    for tag in SHEETS:
        r = report[tag]
        b1v = r["b1"].values()
        b2v = r["b2"].values()
        print(f"{tag:10s} {r['ref']['density_D']:6.3f} "
              f"{r['b2_blind_coverage_mean']:7.4f} "
              f"{np.mean([v['ber_ctx'] for v in b1v]):7.4f} "
              f"{np.mean([v['fa_white_to_ink'] for v in b1v]):7.4f} "
              f"{np.mean([v['miss_ink_to_white'] for v in b1v]):7.4f} "
              f"{np.mean([v['ber'] for v in b2v]):7.4f} "
              f"{np.mean([float(v['runs']['2']['dropout']) for v in b2v]):9.3f}")
    print(f"runtime {report['runtime_s']}s -> build/density_ladder_report.json",
          flush=True)


if __name__ == "__main__":
    _ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    _ap.add_argument("--scan-dir", type=Path, required=True)
    SCANS_DIR = _ap.parse_args().scan_dir
    main()

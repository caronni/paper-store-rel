"""003.0a reanalysis: B1 (c2-K + 16-context detector) on the K4/encode_c2 patch.

Zero-paper step behind the E004 head-to-head: the 003.0 report scored K4/e2
hard-only (0.1110 cell BER, decode_cells_v4 median rule). This script runs the
full v4 soft stage (global GMM + blind 16-context LLRs) on the same scan and
adds the missing piece for M2: a MONOTONE (PAVA/isotonic) LLR recalibration,
evaluated two ways:

  * split-half within the patch (checkerboard cell split; fit on one half,
    score MI on the other, both directions) — no same-cell leakage;
  * cross-sheet: mapping fitted on the 001.4 gridtest c2 reliability tables
    (different sheet, different day), applied to this patch unmodified.

Success criterion (pre-registered in the session dialogue): context-detector
BER at this independent sheet position lands in the 001.4 regime (5.0-5.4%
best-sheet; this is a COLOR-mode scan, so a color-scan penalty like the c3
3.74->4.46 bw->color delta is expected) and recalibrated MI supports B1 >=
~90 b/mm2 class. Numbers land in build/k4e2_context_report.json.

Run (repo root):
  env/bin/python experiments/003-modulation-probes/analyze_k4e2_context.py \\
      <evidence>/scans/test-scan-modprobe.png --e001-build <001's build dir>
(the cross-sheet tables are analyze_gridtest.py's outputs over the 001.4
gridtest scans)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parents[1] / "src"))
sys.path.insert(0, str(_HERE.parents[0] / "001-engine-characterization"))

import scanlab  # noqa: E402

BUILD = _HERE / "build"
CELLS_PER_MM2_C2 = (600.0 / 25.4 / 2.0) ** 2  # 139.5


def pava_nonincreasing(y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Pool-adjacent-violators: weighted least-squares fit, nonincreasing."""
    y = y.astype(np.float64).copy()
    w = w.astype(np.float64).copy()
    blocks = [[i] for i in range(len(y))]
    vals = list(y)
    wts = list(w)
    i = 0
    while i < len(vals) - 1:
        if vals[i] < vals[i + 1] - 1e-15:  # violator (must be nonincreasing)
            merged_w = wts[i] + wts[i + 1]
            merged_v = (vals[i] * wts[i] + vals[i + 1] * wts[i + 1]) / merged_w
            vals[i:i + 2] = [merged_v]
            wts[i:i + 2] = [merged_w]
            blocks[i:i + 2] = [blocks[i] + blocks[i + 1]]
            i = max(i - 1, 0)
        else:
            i += 1
    out = np.empty_like(y)
    for v, b in zip(vals, blocks):
        out[b] = v
    return out


def fit_monotone_map(abs_llr: np.ndarray, err: np.ndarray,
                     n_bins: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """|LLR| -> monotone empirical error probability. Returns (bin centers
    in |LLR|, calibrated p per bin) for interp; p clipped to [1e-5, 0.5]."""
    edges = np.quantile(abs_llr, np.linspace(0.0, 1.0, n_bins + 1))
    edges[-1] += 1e-9
    idx = np.clip(np.searchsorted(edges, abs_llr, side="right") - 1, 0, n_bins - 1)
    centers = np.empty(n_bins)
    emp = np.empty(n_bins)
    wts = np.empty(n_bins)
    for b in range(n_bins):
        sel = idx == b
        wts[b] = max(sel.sum(), 1)
        centers[b] = np.median(abs_llr[sel]) if sel.any() else edges[b]
        emp[b] = err[sel].mean() if sel.any() else 0.5
    p = pava_nonincreasing(emp, wts)
    return centers, np.clip(p, 1e-5, 0.5)


def apply_map(llr: np.ndarray, centers: np.ndarray, p: np.ndarray) -> np.ndarray:
    p_i = np.interp(np.abs(llr), centers, p, left=p[0], right=p[-1])
    return np.sign(llr) * np.log((1.0 - p_i) / p_i)


def mi_bits(llr: np.ndarray, gt_cells: np.ndarray) -> float:
    sgn = 2.0 * gt_cells.astype(np.float64) - 1.0
    return 1.0 - float(np.mean(np.logaddexp(0.0, -sgn * llr))) / np.log(2.0)


def h2(p: float) -> float:
    p = min(max(p, 1e-12), 1 - 1e-12)
    return -p * np.log2(p) - (1 - p) * np.log2(1 - p)


def main(scan_path: Path, e001_build: Path) -> None:
    manifest = json.loads((BUILD / "modprobe_manifest.json").read_text())
    report = json.loads((BUILD / "modprobe_report.json").read_text())
    coef = np.asarray(report["registration"]["affine"], np.float64)
    patch = next(p for p in manifest["patches"] if p["name"] == "K4/encode_c2")
    gt_dots = np.load(BUILD / patch["gt"])
    scan = np.asarray(Image.open(scan_path).convert("L")).astype(np.float32)

    r = scanlab.decode_cells(scan, coef, patch, gt_dots, cell=2)
    soft = r["soft"]
    gt_cells = gt_dots[::2, ::2].astype(np.uint8)
    llr_ctx = np.asarray(soft["llr_ctx"], np.float64)
    err_ctx = (llr_ctx > 0) != gt_cells.astype(bool)

    # Sanity gates: hard BER must reproduce the 003.0 report; shifted-GT null.
    ber_hard_ref = 0.1110
    null = float(((llr_ctx > 0) != np.roll(gt_cells, 7, axis=0).astype(bool)).mean())
    assert abs(r["ber"] - ber_hard_ref) < 0.015, (r["ber"], ber_hard_ref)
    assert 0.45 < null < 0.55, null

    # Split-half monotone recalibration (checkerboard on the cell grid).
    iy, ix = np.mgrid[0:llr_ctx.shape[0], 0:llr_ctx.shape[1]]
    half = ((iy + ix) % 2).astype(bool)
    mi_halves = []
    for train in (half, ~half):
        c, p = fit_monotone_map(np.abs(llr_ctx[train]), err_ctx[train])
        lv = apply_map(llr_ctx[~train], c, p)
        mi_halves.append(mi_bits(lv, gt_cells[~train]))
    mi_recal_split = float(np.mean(mi_halves))

    # Cross-sheet recalibration from the 001.4 gridtest c2 reliability tables.
    cross = {}
    for tag in ("gridtest", "gridtest-direct"):
        f = (e001_build / f"analysis-test-scan-{tag}" / "encode_c2_v4_metrics.json")
        if not f.exists():
            continue
        m4 = json.loads(f.read_text())["v4"]
        rel = m4.get("reliability_ctx") or m4.get("reliability")
        if not rel:
            continue
        centers = np.array([(b["llr_lo"] + b["llr_hi"]) / 2.0 for b in rel])
        p = np.clip(pava_nonincreasing(
            np.array([b["emp_err"] for b in rel]),
            np.array([max(b.get("n", 1), 1) for b in rel])), 1e-5, 0.5)
        lv = apply_map(llr_ctx, centers, p)
        cross[tag] = {"mi_recal_bits": mi_bits(lv, gt_cells),
                      "ber_sign": float(((lv > 0) != gt_cells.astype(bool)).mean())}

    ber_ctx = float(err_ctx.mean())
    out = {
        "patch": patch["name"],
        "scan": scan_path.name,
        "scan_mode_note": "1200dpi COLOR scan converted to grey - expect a "
                          "color-mode penalty vs 001.4's grey scans (c3 "
                          "measured 3.74 bw vs 4.46 color on this sheet's day)",
        "hard": {"ber": float(r["ber"]), "ref_003_report": ber_hard_ref,
                 "null_shifted_gt": null},
        "context": {
            "ber": ber_ctx,
            "ber_001_4_reference": [0.0496, 0.0541],
            "mi_bits_raw": float(soft["mi_bits_ctx"]),
            "mi_bits_recal_splithalf": mi_recal_split,
            "bsc_proxy_bits": 1.0 - h2(ber_ctx),
        },
        "global": {"ber": float(soft["ber_llr"]),
                   "mi_bits_raw": float(soft["mi_bits"])},
        "cross_sheet_recal": cross,
        "areal_bits_per_mm2": {
            "cells_per_mm2": CELLS_PER_MM2_C2,
            "bsc_proxy": (1.0 - h2(ber_ctx)) * CELLS_PER_MM2_C2,
            "mi_recal_splithalf": mi_recal_split * CELLS_PER_MM2_C2,
            "mi_raw_ctx": float(soft["mi_bits_ctx"]) * CELLS_PER_MM2_C2,
        },
        "steps_detected": len(r.get("steps", [])),
        "reliability_ctx_recal_check": None,
    }
    (BUILD / "k4e2_context_report.json").write_text(json.dumps(out, indent=1))

    print(f"K4/e2 (c2, 330x330 dots, {gt_cells.size} cells) - B1 at an "
          f"independent sheet position, color-mode scan:")
    print(f"  hard BER          {out['hard']['ber']:.4f}  (003.0 report {ber_hard_ref}; null {null:.3f})")
    print(f"  context BER       {ber_ctx:.4f}  (001.4 grey-scan ref 0.050-0.054)")
    print(f"  BSC proxy         {out['context']['bsc_proxy_bits']:.3f} b/cell = "
          f"{out['areal_bits_per_mm2']['bsc_proxy']:.1f} b/mm2")
    print(f"  MI ctx raw        {out['context']['mi_bits_raw']:.3f} b/cell = "
          f"{out['areal_bits_per_mm2']['mi_raw_ctx']:.1f} b/mm2")
    print(f"  MI ctx recal(s/h) {mi_recal_split:.3f} b/cell = "
          f"{out['areal_bits_per_mm2']['mi_recal_splithalf']:.1f} b/mm2")
    for tag, d in cross.items():
        print(f"  MI cross-sheet [{tag}]: {d['mi_recal_bits']:.3f} b/cell "
              f"({d['mi_recal_bits'] * CELLS_PER_MM2_C2:.1f} b/mm2)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("scan", type=Path)
    ap.add_argument("--e001-build", type=Path, required=True)
    args = ap.parse_args()
    main(args.scan, args.e001_build)

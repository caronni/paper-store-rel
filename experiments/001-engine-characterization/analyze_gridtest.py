#!/usr/bin/env python
"""Analyze a gridtest scan (runs 001.2/001.3, decoder study 001.4):
registration -> patch metrics -> encode-patch BER via the scanlab decoder,
v3 (dense poly2 warp) vs v4 (stepped warp + blind soft output) side by side.

Usage:
    python analyze_gridtest.py <evidence>/scans/test-scan-gridtest-direct.png
Outputs a metrics report to stdout and, per encode patch, error maps /
overlays (v3 + v4), a y-residual-profile plot, and a v4 metrics JSON to
build/analysis-<scan-stem>/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import scanlab

Image.MAX_IMAGE_PIXELS = None
HERE = Path(__file__).parent
BUILD = HERE / "build"

NOMINAL_INK = {"vlines": 0.5, "hlines": 0.5, "checker": 0.5}
UNCERTAIN_TARGETS = {"encode_c3": (0.05, 0.10), "encode_c2": (0.15, 0.25)}


def rand_clustered(p: float) -> float:
    """Expected 'clustered' fraction for i.i.d. errors at rate p (>=1 of 4 nbrs)."""
    return 1.0 - (1.0 - p) ** 4


def conf_at_target(llr: np.ndarray, e_llr: np.ndarray, u_target: float
                   ) -> tuple[float, float, float]:
    """(uncertain_frac, llr_thresh, ber_confident) at an uncertain-mass target."""
    t = float(np.quantile(np.abs(llr), u_target))
    sel = np.abs(llr) >= t
    return float(1.0 - sel.mean()), t, float(e_llr[sel].mean())


def save_errmap(err_map: np.ndarray, path: Path) -> None:
    img = ((1 - np.kron(err_map, np.ones((4, 4)))) * 255).astype(np.uint8)
    Image.fromarray(img).save(path)


def save_overlay(r: dict, white: float, black: float, path: Path) -> None:
    sn = np.clip((np.kron(r["means"], np.ones((4, 4))) - black) / (white - black), 0, 1)
    gu = np.kron(r["gt_cells"], np.ones((4, 4), np.float32))
    Image.fromarray((np.clip((sn + gu) / 2, 0, 1) * 255).astype(np.uint8)).save(path)


def plot_yprofile(path: Path, h_dots: int, yprof: dict, steps: list,
                  win_prof: tuple[np.ndarray, np.ndarray]) -> None:
    """PIL line plot: r(y) raw (blue) + median-filtered (black), window-row
    profile medians (red circles), detected steps (green verticals)."""
    W, H, ml, mr, mt, mb = 1100, 340, 52, 12, 12, 32
    rmax = 1.6
    img = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(img)

    def px(y_dots: float) -> float:
        return ml + (W - ml - mr) * y_dots / h_dots

    def py(r_dots: float) -> float:
        r = min(max(r_dots, -rmax), rmax)
        return mt + (H - mt - mb) * (rmax - r) / (2 * rmax)

    for r in (-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5):
        grey = (170, 170, 170) if r == 0 else (228, 228, 228)
        dr.line([(px(0), py(r)), (px(h_dots), py(r))], fill=grey)
        dr.text((4, py(r) - 6), f"{r:+.1f}", fill=(120, 120, 120))
    for yd in range(0, h_dots + 1, 100):
        dr.text((px(yd) - 10, H - mb + 4), str(yd), fill=(120, 120, 120))
    for y, mag in steps:
        dr.line([(px(y), mt), (px(y), H - mb)], fill=(0, 150, 0))
        dr.text((px(y) + 2, mt + 2), f"{mag:+.2f}", fill=(0, 120, 0))
    dr.line([(px(y), py(r)) for y, r in zip(yprof["y_dots"], yprof["r_dots"])],
            fill=(150, 150, 255))
    dr.line([(px(y), py(r)) for y, r in zip(yprof["y_dots"], yprof["r_med_dots"])],
            fill=(0, 0, 0), width=2)
    for y, v in zip(*win_prof):
        dr.ellipse([px(y) - 3, py(v) - 3, px(y) + 3, py(v) + 3], outline=(200, 0, 0))
    dr.text((ml, H - mb + 16), "y [dots] — r(y) residual after poly2 [dots]; "
            "black=median5, blue=raw band xcorr, red=window-row medians, green=steps",
            fill=(90, 90, 90))
    img.save(path)


def main(scan_path: Path) -> None:
    scan = np.asarray(Image.open(scan_path).convert("L")).astype(np.float32)
    man = json.load(open(BUILD / "gridtest_manifest.json"))
    patches = {p["name"]: p for p in man["patches"]}
    outdir = BUILD / f"analysis-{scan_path.stem}"
    outdir.mkdir(parents=True, exist_ok=True)

    coef, white, black = scanlab.register_fiducials(scan, man)
    thr = (white + black) / 2
    a, b, _, d, e, _ = coef
    print(f"registered: scale=({np.hypot(a, d)/scanlab.S:.5f},{np.hypot(b, e)/scanlab.S:.5f}) "
          f"rot={np.degrees(np.arctan2(d, a)):.3f} deg  white={white:.0f} black={black:.0f}")

    print("\n-- periodic families: interior ink fraction (nominal 0.5) --")
    for fam in ("vlines", "hlines", "checker"):
        row = []
        for n in (1, 2, 3, 4):
            p = patches[f"{fam}_n{n}"]
            img = scanlab.warp_dots(scan, coef, p["x_dots"] + 8, p["y_dots"] + 8,
                                    p["w_dots"] - 16, p["h_dots"] - 16)
            row.append(f"n{n}={float((img < thr).mean()):.3f}")
        print(f"  {fam:8} " + "  ".join(row))

    print("\n-- dots / holes: feature-pixel survival --")
    for fam in ("dots", "holes"):
        row = []
        for n in (1, 2, 3, 4):
            p = patches[f"{fam}_n{n}"]
            img = scanlab.warp_dots(scan, coef, p["x_dots"], p["y_dots"], p["w_dots"], p["h_dots"])
            gt = np.load(BUILD / f"gridtest_gt/{fam}_n{n}.npy")
            gt2 = np.kron(gt, np.ones((2, 2), np.uint8))[: img.shape[0], : img.shape[1]]
            feat = img[gt2 == 1]
            surv = float((feat < thr).mean() if fam == "dots" else (feat > thr).mean())
            row.append(f"n{n}={surv:.3f}")
        print(f"  {fam:8} " + "  ".join(row))

    print("\n-- encode patches: v3 vs v4 decode --")
    print(f"  {'patch':<11} {'dec':<3} {'BER':<7} {'errors':<12} {'clus':<5} "
          f"{'rand':<5} {'windows':<8} {'y-resid RMS':<11}")
    for name, cell in (("encode_c3", 3), ("encode_c2", 2)):
        p = patches[name]
        gt = np.load(BUILD / f"gridtest_gt/{name}.npy")
        r3 = scanlab.decode_cells(scan, coef, p, gt, cell, win_y=128, step_y=64,
                                  edge_windows=False, y_profile=False,
                                  soft=False, diagnostics=False)
        r4 = scanlab.decode_cells(scan, coef, p, gt, cell)
        for tag, r in (("v3", r3), ("v4", r4)):
            print(f"  {name:<11} {tag:<3} {r['ber']:.4f}  "
                  f"{r['errors']}/{r['cells']:<6} {r['clustered']:>4.0%} "
                  f"{rand_clustered(r['ber']):>4.0%} "
                  f"{r['warp_windows_used']}/{r['warp_windows_total']:<4} "
                  f"{r['poly_resid_rms_dots']:.2f} dots")

        s = r4["soft"]
        gmm = s["gmm"]
        e_llr = (s["llr"] > 0) != r4["gt_cells"].astype(bool)
        print(f"    soft: GMM mu={gmm['mu'][0]:.3f}/{gmm['mu'][1]:.3f} "
              f"sig={gmm['sigma'][0]:.3f}/{gmm['sigma'][1]:.3f} "
              f"pi={gmm['pi'][0]:.2f}/{gmm['pi'][1]:.2f} "
              f"({gmm['n_iters']} iters, dmu {gmm['dmu_last_iter']:.1e}, "
              f"{'converged' if gmm['converged'] else 'NOT converged'})")
        print(f"    soft: BER median-thr={r4['ber']:.4f}  LLR-sign={s['ber_llr']:.4f} "
              f"(delta {100 * (s['ber_llr'] - r4['ber']):+.2f}pp)  "
              f"MI={s['mi_bits']:.3f} bits/cell")
        print(f"    ctx : BER LLR-sign={s['ber_llr_ctx']:.4f} "
              f"({100 * (s['ber_llr_ctx'] - s['ber_llr']):+.2f}pp vs global LLR)  "
              f"MI={s['mi_bits_ctx']:.3f} bits/cell")
        e_ctx = (s["llr_ctx"] > 0) != r4["gt_cells"].astype(bool)
        targets, targets_ctx = {}, {}
        for u in UNCERTAIN_TARGETS[name]:
            uf, t, bc = conf_at_target(s["llr"], e_llr, u)
            targets[f"{u:.2f}"] = {"uncertain_frac": uf, "llr_thresh": t,
                                   "ber_confident": bc}
            ufc, tc, bcc = conf_at_target(s["llr_ctx"], e_ctx, u)
            targets_ctx[f"{u:.2f}"] = {"uncertain_frac": ufc, "llr_thresh": tc,
                                       "ber_confident": bcc}
            print(f"    soft: confident BER={bc:.4f} (ctx {bcc:.4f}) at "
                  f"uncertain={uf:.1%} (target {u:.0%}, |LLR|>={t:.2f})")
        steps = r4["steps"]
        cat = ", ".join(f"(y={y:.0f}, {mag:+.2f}d)" for y, mag in steps) or "none"
        print(f"    steps (|d(median5 r)|>0.25 dots): {cat}")

        save_errmap(r3["err_map"], outdir / f"{name}_errmap.png")
        save_overlay(r3, white, black, outdir / f"{name}_overlay.png")
        save_errmap(r4["err_map"], outdir / f"{name}_errmap_v4.png")
        save_errmap(e_ctx, outdir / f"{name}_errmap_v4ctx.png")
        save_overlay(r4, white, black, outdir / f"{name}_overlay_v4.png")
        dy = r4["diag_yprof"]
        plot_yprofile(outdir / f"{name}_yprofile_v4.png", p["h_dots"], dy, steps,
                      r4["yprof_win_dots"])
        metrics = {
            "scan": scan_path.name, "patch": name, "cell_dots": cell,
            "v3": {"ber": r3["ber"], "errors": r3["errors"], "cells": r3["cells"],
                   "clustered": r3["clustered"],
                   "poly_resid_rms_dots": r3["poly_resid_rms_dots"]},
            "v4": {"ber": r4["ber"], "errors": r4["errors"], "cells": r4["cells"],
                   "clustered": r4["clustered"],
                   "clustered_random_expect": rand_clustered(r4["ber"]),
                   "poly_resid_rms_dots": r4["poly_resid_rms_dots"],
                   "ber_llr": s["ber_llr"], "mi_bits": s["mi_bits"],
                   "ber_llr_ctx": s["ber_llr_ctx"], "mi_bits_ctx": s["mi_bits_ctx"],
                   "gmm": gmm, "conf_curve": s["conf_curve"],
                   "conf_curve_ctx": s["conf_curve_ctx"],
                   "conf_at_targets": targets, "conf_at_targets_ctx": targets_ctx,
                   "reliability": s["reliability"],
                   "reliability_ctx": s["reliability_ctx"],
                   "steps_y_mag_dots": steps,
                   "yprofile": {"y_dots": dy["y_dots"].tolist(),
                                "r_dots": dy["r_dots"].tolist(),
                                "r_med_dots": dy["r_med_dots"].tolist()},
                   "yprof_win_dots": [r4["yprof_win_dots"][0].tolist(),
                                      r4["yprof_win_dots"][1].tolist()]},
        }
        (outdir / f"{name}_v4_metrics.json").write_text(json.dumps(metrics, indent=1))
    print(f"\nartifacts in {outdir}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))

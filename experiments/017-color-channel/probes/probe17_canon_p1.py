# Historical record of e017 (017.4, the Canon 4800 re-anchoring), retired from scratch/ 2026-10-09;
# inputs in the evidence archive. Regenerates build/probe17_out/canon-p1.json with:
#   PYTHONPATH=src:. env/bin/python experiments/017-color-channel/probes/probe17_canon_p1.py --evidence-root DIR [n_tiles]   (after probe17_canon_prep.py)
"""probe17_canon_p1: 017.4 P1-Canon — Stage-A word-site LUMA margin (W vs the
frozen CM dark rendering) at the real footing, e004 A3 tiles, Canon 4800 RGB.

Machinery: probe17_canon_p5.warp_square_means (dense warp on the 4x-dec crop,
dual-footing 6x6 interior-grid means) on the LUMA reduction against the
C|M|Y union GT; probe17_stagea_luma.measure_window verbatim for the
statistics (oracle threshold, pinned 2-GMM all-cells, pinned 2-GMM balanced
site population, exact-binomial (100,23) t=13 word-fail, rolled-GT null).

Flatbed baseline (probes/probe17_out/p1-e004-home.json class): fixed-CM home
median ~6.4% at the Stage-A statistic.

Usage: env/bin/python experiments/017-color-channel/probes/probe17_canon_p1.py --evidence-root DIR [n_tiles]
Writes experiments/017-color-channel/build/probe17_out/canon-p1.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
for rel in ("experiments/004-finalists-checkerboard",
            "experiments/002-calibration-page",
            "experiments/003-modulation-probes",
            "experiments/001-engine-characterization",
            "experiments/006-loop-pages",
            "experiments/017-color-channel/probes",
            "src"):
    p = str(REPO / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

import tifffile                                   # noqa: E402
import analyze_e004 as ae                         # noqa: E402
import cal_core as cc                             # noqa: E402
import probe17_canon_p5 as base                   # noqa: E402
import probe17_stagea_luma as p1                  # noqa: E402

SCAN_REL = "paper-store-evidence-paperholo-era/004-finalists-checkerboard/finalists/captures/finalists-canon-4800rgb.tiff"   # under --evidence-root
OUT = REPO / "experiments/017-color-channel/build" / "probe17_out"
STATES7 = ("W", "C", "M", "Y", "CM", "CY", "MY")


def crop_luma(mm, coef, x0d, y0d, x1d, y1d):
    corners = np.array([[x0d, y0d], [x1d, y0d], [x0d, y1d], [x1d, y1d]])
    px = cc.affine_apply(coef, corners)
    x0, y0 = int(px[:, 0].min()), int(px[:, 1].min())
    x1, y1 = int(np.ceil(px[:, 0].max())), int(np.ceil(px[:, 1].max()))
    blk = np.asarray(mm[y0:y1, x0:x1], np.float32)
    arr = (blk[..., 0] + blk[..., 1] + blk[..., 2]) / 3.0
    loc = coef.copy()
    loc[2] -= x0
    loc[5] -= y0
    return arr, loc


def rect_means_luma(mm, manifest, name: str) -> dict[str, np.ndarray]:
    e = cc.entry(manifest, f"{name}_C")
    gts = [cc.load_gt(cc.entry(manifest, f"{name}_{p}")) for p in "CMY"]
    gt = (gts[0] | gts[1] | gts[2]).astype(np.uint8)
    cell = int(e["params"]["cell_dots"])
    x, y, w, h = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
    arr_nat, loc_nat = crop_luma(
        mm, base.COEF_NAT, x - base.MARGIN_DOTS, y - base.MARGIN_DOTS,
        x + w + base.MARGIN_DOTS, y + h + base.MARGIN_DOTS)
    arr_dec = base.box_dec(arr_nat, base.F)
    loc_dec = loc_nat.copy() / base.F
    loc_dec[2] = (loc_nat[2] - (base.F - 1) / 2) / base.F
    loc_dec[5] = (loc_nat[5] - (base.F - 1) / 2) / base.F
    out_t = base.warp_square_means(arr_dec, loc_dec, arr_nat, loc_nat,
                                   x, y, gt[:w], cell)
    out_b = base.warp_square_means(arr_dec, loc_dec, arr_nat, loc_nat,
                                   x, y + h - w, gt[h - w:], cell)
    split = (h // 2) // cell
    off = (h - w) // cell
    return {tag: np.concatenate([out_t[tag][:split],
                                 out_b[tag][split - off:]], axis=0)
            for tag in ("dec", "nat")}


def _scan_tiff() -> Path:
    """The e004 Canon 4800 capture under --evidence-root (strips the flag from argv)."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import argparse
    from measure import _evidence
    ap = argparse.ArgumentParser()
    _evidence.add_argument(ap)
    a, sys.argv[1:] = ap.parse_known_args()
    scan = _evidence.resolve(a.evidence_root, tool=Path(__file__).stem) / SCAN_REL
    _evidence.need(scan, tool=Path(__file__).stem)
    return scan


def main() -> None:
    scan_tiff = _scan_tiff()
    OUT.mkdir(parents=True, exist_ok=True)
    n_tiles = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    t0 = time.time()
    mm = tifffile.memmap(scan_tiff, mode="r")
    manifest = cc.load_manifest(ae.MANIFEST_PATH)
    tiles = ae.tiles_of(manifest, "A3")[:n_tiles]
    res: dict = {"probe": "P1-Canon", "date": "2026-07-10",
                 "scan_sha256": "e1f14f1c57ffcefeac25d66a236bdadf01765454"
                                "893d152856dcfefca360b4ba",
                 "footings": {"nat": {"windows": {}},
                              "dec": {"windows": {}}}}
    for t in tiles:
        name = t["name"]
        e0 = cc.entry(manifest, f"{name}_C")
        states = cc.load_gt_named(e0["params"]["states_gt"],
                                  ae.BUILD).astype(np.int64)
        names = np.array(STATES7, dtype=object)[states.ravel()]
        m = rect_means_luma(mm, manifest, name)
        for tag in ("nat", "dec"):
            win = p1.measure_window(m[tag].ravel(), names)
            res["footings"][tag]["windows"][name] = win
        wn = res["footings"]["nat"]["windows"][name]
        wd = res["footings"]["dec"]["windows"][name]
        print(f"{name}: CM nat oracle {wn['CM']['ber_oracle']:.4f} "
              f"gmm-sites {wn['CM'].get('ber_gmm_sites', float('nan')):.4f} "
              f"| dec oracle {wd['CM']['ber_oracle']:.4f} "
              f"gmm-sites {wd['CM'].get('ber_gmm_sites', float('nan')):.4f} "
              f"({time.time()-t0:.0f}s)", flush=True)
    # summaries
    for tag in ("nat", "dec"):
        wins = res["footings"][tag]["windows"]
        summ = {}
        for key in ("ber_oracle", "ber_gmm_all", "ber_gmm_sites"):
            vals = [w["CM"][key] for w in wins.values() if key in w["CM"]]
            if not vals:
                continue
            summ[key] = {"median": float(np.median(vals)),
                         "worst": float(max(vals)),
                         "wf_median": p1.word_fail(float(np.median(vals))),
                         "wf_worst": p1.word_fail(float(max(vals)))}
        nulls = [w.get("null_rolled_ber") for w in wins.values()
                 if w.get("null_rolled_ber") is not None]
        summ["null_rolled_ber_range"] = [float(min(nulls)), float(max(nulls))]
        res["footings"][tag]["summary_CM"] = summ
        print(f"[{tag}] CM summary: " + json.dumps(summ, default=float),
              flush=True)
    (OUT / "canon-p1.json").write_text(json.dumps(res, indent=1,
                                                  default=float))
    print(f"-> {OUT / 'canon-p1.json'}", flush=True)


if __name__ == "__main__":
    main()

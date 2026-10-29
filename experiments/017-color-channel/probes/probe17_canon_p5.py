# Historical record of e017 (017.4, the Canon 4800 re-anchoring), retired from scratch/ 2026-10-09;
# inputs in the evidence archive. Regenerates build/probe17_out/canon-p5.json with:
#   PYTHONPATH=src:. env/bin/python experiments/017-color-channel/probes/probe17_canon_p5.py --evidence-root DIR [n_tiles] [--no-ldpc]   (after probe17_canon_prep.py)
"""probe17_canon_p5: 017.4 P5-Canon — per-LEVEL (C/M/Y presence-bit) rates
at the REAL footing (Canon 4800 dpi RGB = 8 px/dot), e004 A3 7-state c3,
16 tiles, cross-tile QDA (the legal footing; machinery per analyze_e004 /
probe17_level_rates).

Two legs, same registration (probe17_canon_reg.json):
  dec2400=OFF here — the two measured footings are
  * "dec" : 4x box-decimated crops = 2 px/dot (the flatbed-anchor footing,
    through the Canon; scanner-vs-scanner comparison)
  * "nat" : native 8 px/dot crops
  BOTH use the SAME warp field (scanlab dense-warp v4 machinery verbatim,
  estimated on the decimated crop — warp offsets are in dot units, footing-
  invariant) and the SAME mean estimator (6x6 interior grid, +-3/8 cell):
  the footing is the ONLY difference.

Per level: hard bit BER (posterior-marginal), miss/fa, per-tile spread,
soft MI raw + split-half-PAVA calibrated, LDPC rung overlay (measured
calibrated LLRs on real ladder codewords, 4096-cell raster blocks).

Usage: env/bin/python experiments/017-color-channel/probes/probe17_canon_p5.py --evidence-root DIR [n_tiles] [--no-ldpc]
Writes experiments/017-color-channel/build/probe17_out/canon-p5.json
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
            "experiments/017-color-channel/probes", "src"):
    p = str(REPO / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

import tifffile                                     # noqa: E402
import analyze_e004 as ae                           # noqa: E402
import cal_core as cc                               # noqa: E402
import analyze_k4e2_context as k4                   # noqa: E402
import scanlab                                      # noqa: E402
import probe17_level_rates as p5                    # noqa: E402

SCAN_REL = "paper-store-evidence-paperholo-era/004-finalists-checkerboard/finalists/captures/finalists-canon-4800rgb.tiff"   # under --evidence-root
DEC_PNG = REPO / "experiments/017-color-channel/build" / "probe17_canon_dec1200.png"
REG = json.loads((REPO / "experiments/017-color-channel/build" / "probe17_canon_reg.json").read_text())
OUT = REPO / "experiments/017-color-channel/build" / "probe17_out"
COEF_NAT = np.asarray(REG["affine_native4800"], np.float64)
F = 4
MARGIN_DOTS = 16
MEAN_GRID = 6
CHAN_IDX = {"C": 0, "M": 1, "Y": 2}   # C reads in R, M in G, Y in B
LEVELS = "CMY"


def box_dec(a: np.ndarray, f: int) -> np.ndarray:
    h, w = a.shape[0] // f * f, a.shape[1] // f * f
    return a[:h, :w].reshape(h // f, f, w // f, f).mean(axis=(1, 3))


def crop_channel(mm, coef, x0d, y0d, x1d, y1d, chan: int):
    """Native crop of one RGB channel + the crop-local affine."""
    corners = np.array([[x0d, y0d], [x1d, y0d], [x0d, y1d], [x1d, y1d]])
    px = cc.affine_apply(coef, corners)
    x0, y0 = int(px[:, 0].min()), int(px[:, 1].min())
    x1, y1 = int(np.ceil(px[:, 0].max())), int(np.ceil(px[:, 1].max()))
    arr = np.asarray(mm[y0:y1, x0:x1, chan], np.float32)
    loc = coef.copy()
    loc[2] -= x0
    loc[5] -= y0
    return arr, loc


def warp_square_means(arr_dec, coef_dec, arr_nat, coef_nat, x_dots, y_dots,
                      gt_sq: np.ndarray, cell: int) -> dict[str, np.ndarray]:
    """scanlab.decode_cells v4 dense-warp (verbatim warp stage, 2 px/dot on
    the decimated crop), then n x n interior-grid cell means sampled from
    BOTH footings with the SAME warp. Square patches only."""
    from scipy.ndimage import map_coordinates
    gt = gt_sq.astype(np.float32)
    h, w = gt.shape
    assert h == w
    nc = h // cell
    win_x, win_y, step_x, step_y = 128, 64, 64, 32
    ys = list(range(win_y // 2, h - win_y // 2 + 1, step_y))
    xs = list(range(win_x // 2, w - win_x // 2 + 1, step_x))
    if ys[-1] != h - win_y // 2:
        ys.append(h - win_y // 2)
    if xs[-1] != w - win_x // 2:
        xs.append(w - win_x // 2)
    pts, offs = [], []
    for wy in ys:
        for wx in xs:
            sw = scanlab.warp_dots(arr_dec, coef_dec, x_dots + wx - win_x // 2,
                                   y_dots + wy - win_y // 2, win_x, win_y)
            tpl = np.kron(1 - gt[wy - win_y // 2: wy + win_y // 2,
                                 wx - win_x // 2: wx + win_x // 2],
                          np.ones((2, 2), np.float32)) * 255
            dy, dx, q = scanlab.xcorr_offset(sw, tpl)
            if q > 0.02:
                pts.append((wx, wy))
                offs.append((dx / 2, dy / 2))
    pts, offs = np.array(pts, float), np.array(offs, float)

    def design(xy):
        x, y = xy[:, 0] / w, xy[:, 1] / h
        return np.column_stack([np.ones_like(x), x, y, x * y, x * x, y * y])

    keep = np.ones(len(pts), bool)
    cx_ = cy_ = None
    for _ in range(2):
        D = design(pts[keep])
        cx_, *_ = np.linalg.lstsq(D, offs[keep, 0], rcond=None)
        cy_, *_ = np.linalg.lstsq(D, offs[keep, 1], rcond=None)
        rx = offs[:, 0] - design(pts) @ cx_
        ry = offs[:, 1] - design(pts) @ cy_
        keep = np.hypot(rx, ry) < max(1.5,
                                      np.percentile(np.hypot(rx, ry)[keep], 90))
    ry_all = offs[:, 1] - design(pts) @ cy_
    prof_wy = np.array(sorted(set(pts[keep][:, 1])))
    prof_v = np.array([np.median(ry_all[keep & (pts[:, 1] == wy)])
                       for wy in prof_wy])
    gy, gx = np.mgrid[0:nc, 0:nc].astype(np.float64)
    ccx = gx * cell + cell / 2
    ccy = gy * cell + cell / 2
    Dc = design(np.column_stack([ccx.ravel(), ccy.ravel()]))
    wx_ = (Dc @ cx_).reshape(nc, nc)
    wy_ = (Dc @ cy_).reshape(nc, nc) + np.interp(ccy[:, 0], prof_wy,
                                                 prof_v)[:, None]
    # n x n interior grid means (+-3/8 cell), both footings, same warp
    offs_1d = np.linspace(-0.375, 0.375, MEAN_GRID) * cell
    out = {}
    for tag, arr, coef in (("dec", arr_dec, coef_dec),
                           ("nat", arr_nat, coef_nat)):
        a, b, c, d, e, f = coef
        acc = np.zeros((nc, nc))
        for oy in offs_1d:
            for ox in offs_1d:
                px_ = x_dots + ccx + wx_ + ox
                py_ = y_dots + ccy + wy_ + oy
                acc += map_coordinates(arr, [d * px_ + e * py_ + f,
                                             a * px_ + b * py_ + c],
                                       order=1, mode="nearest")
        out[tag] = acc / MEAN_GRID ** 2
    out["warp_windows_used"] = int(keep.sum())
    out["poly_resid_rms_dots"] = float(np.sqrt(np.mean(ry_all[keep] ** 2)))
    return out


def rect_means(mm, manifest, name: str, plane: str) -> dict[str, np.ndarray]:
    """decode_rect_by_squares construction (2 overlapping squares stitched at
    the overlap midline), dual-footing means."""
    e = cc.entry(manifest, f"{name}_{plane}")
    gt = cc.load_gt(e)
    cell = int(e["params"]["cell_dots"])
    x, y, w, h = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
    assert h > w and (h - w) % cell == 0 and w % cell == 0
    arr_nat, loc_nat = crop_channel(
        mm, COEF_NAT, x - MARGIN_DOTS, y - MARGIN_DOTS,
        x + w + MARGIN_DOTS, y + h + MARGIN_DOTS, CHAN_IDX[plane])
    arr_dec = box_dec(arr_nat, F)
    loc_dec = loc_nat.copy() / F
    loc_dec[2] = (loc_nat[2] - (F - 1) / 2) / F
    loc_dec[5] = (loc_nat[5] - (F - 1) / 2) / F
    out_t = warp_square_means(arr_dec, loc_dec, arr_nat, loc_nat,
                              x, y, gt[:w], cell)
    out_b = warp_square_means(arr_dec, loc_dec, arr_nat, loc_nat,
                              x, y + h - w, gt[h - w:], cell)
    split = (h // 2) // cell
    off = (h - w) // cell
    res = {}
    for tag in ("dec", "nat"):
        res[tag] = np.concatenate([out_t[tag][:split],
                                   out_b[tag][split - off:]], axis=0)
    res["warp_windows_used"] = out_t["warp_windows_used"] \
        + out_b["warp_windows_used"]
    res["poly_resid_rms_dots"] = max(out_t["poly_resid_rms_dots"],
                                     out_b["poly_resid_rms_dots"])
    return res


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
    n_tiles = 16
    do_ldpc = "--no-ldpc" not in sys.argv
    for a_ in sys.argv[1:]:
        if a_.isdigit():
            n_tiles = int(a_)
    t0 = time.time()
    mm = tifffile.memmap(scan_tiff, mode="r")
    manifest = cc.load_manifest(ae.MANIFEST_PATH)
    # registered decimated scan: white model only (registration already
    # frozen in probe17_canon_reg.json = the same cal_core run)
    scan = cc.load_scan(DEC_PNG, compute_sha256=False)
    cc.register(scan, manifest)
    wm = cc.white_model(scan)
    tiles = ae.tiles_of(manifest, "A3")[:n_tiles]

    feats = {"dec": [], "nat": []}
    shapes, names = [], []
    for t in tiles:
        e0 = cc.entry(manifest, f"{t['name']}_C")
        states = cc.load_gt_named(e0["params"]["states_gt"],
                                  ae.BUILD).astype(np.int64)
        cell = int(e0["params"]["cell_dots"])
        Xs = {"dec": [], "nat": []}
        ww, rr = 0, 0.0
        for plane in "CMY":
            r = rect_means(mm, manifest, t["name"], plane)
            e = cc.entry(manifest, f"{t['name']}_{plane}")
            nc_y, nc_x = r["nat"].shape
            xg, yg = np.meshgrid(
                e["x_dots"] + (np.arange(nc_x) + 0.5) * cell,
                e["y_dots"] + (np.arange(nc_y) + 0.5) * cell)
            white = cc.white_at(wm, xg, yg, "rgb"[CHAN_IDX[plane]])
            for tag in ("dec", "nat"):
                D = -np.log10(np.maximum(r[tag], 1.0)
                              / np.maximum(white, 1e-3))
                Xs[tag].append(D.ravel())
            ww += r["warp_windows_used"]
            rr = max(rr, r["poly_resid_rms_dots"])
        assert Xs["nat"][0].size == states.size
        for tag in ("dec", "nat"):
            feats[tag].append((np.stack(Xs[tag], axis=1), states.ravel()))
        shapes.append(states.shape)
        names.append(t["name"])
        print(f"features {t['name']}: {feats['nat'][-1][0].shape} "
              f"warp_wins {ww} resid {rr:.3f}d "
              f"({time.time()-t0:.0f}s)", flush=True)

    report: dict = {"probe": "P5-Canon", "date": "2026-07-10",
                    "scan_sha256": "e1f14f1c57ffcefeac25d66a236bdadf01765454"
                                   "893d152856dcfefca360b4ba",
                    "n_tiles": len(tiles), "mean_grid": MEAN_GRID,
                    "footings": {}}
    half_tiles = [p5.checkerboard(s) for s in shapes]
    for tag, label in (("nat", "native 8 px/dot"),
                       ("dec", "4x box-dec 2 px/dot (anchor footing)")):
        # cross-tile QDA
        llr_tiles = {p: [] for p in LEVELS}
        g_tiles = {p: [] for p in LEVELS}
        state_conf = np.zeros((7, 7), np.int64)
        for hold in range(len(feats[tag])):
            Xtr = np.concatenate([X for i, (X, _) in enumerate(feats[tag])
                                  if i != hold])
            ytr = np.concatenate([y for i, (_, y) in enumerate(feats[tag])
                                  if i != hold])
            Xte, yte = feats[tag][hold]
            model = ae.GaussianQDA().fit(Xtr, ytr, 7)
            bit_llrs = p5.qda_posterior_llrs(model, Xte)
            pred = model.predict(Xte)
            np.add.at(state_conf, (yte, pred), 1)
            for i, p in enumerate(LEVELS):
                llr_tiles[p].append(bit_llrs[i])
                g_tiles[p].append(p5.MEMBER[p][yte])
        acc7 = float(np.trace(state_conf) / state_conf.sum())
        frec: dict = {"label": label, "acc_7state_crosstile": acc7,
                      "state_confusion": state_conf.tolist(), "levels": {}}
        for p in LEVELS:
            llr_all = np.concatenate(llr_tiles[p])
            g_all = np.concatenate(g_tiles[p])
            half_all = np.concatenate(half_tiles)
            err = (llr_all > 0) != g_all.astype(bool)
            per_tile = [float((((l > 0) != g.astype(bool))).mean())
                        for l, g in zip(llr_tiles[p], g_tiles[p])]
            cal_all = p5.calibrate_splithalf(llr_all, g_all, half_all)
            rec = {"ber": float(err.mean()),
                   "per_tile_ber": {n: round(b, 5)
                                    for n, b in zip(names, per_tile)},
                   "ber_tile_min": float(min(per_tile)),
                   "ber_tile_max": float(max(per_tile)),
                   "miss": float(err[g_all == 1].mean()),
                   "fa": float(err[g_all == 0].mean()),
                   "mi_raw_bits": float(k4.mi_bits(llr_all, g_all)),
                   "mi_cal_splithalf_bits": float(k4.mi_bits(cal_all, g_all))}
            if do_ldpc:
                cal_tiles, off = [], 0
                for g in g_tiles[p]:
                    cal_tiles.append(cal_all[off:off + g.size])
                    off += g.size
                rec["ldpc_measured"] = p5.ldpc_overlay(cal_tiles, g_tiles[p],
                                                       p5.RUNGS)
            frec["levels"][p] = rec
            print(f"[{tag}] level {p}: BER {rec['ber']:.4f} "
                  f"(tiles {rec['ber_tile_min']:.4f}-{rec['ber_tile_max']:.4f}) "
                  f"miss {rec['miss']:.4f} fa {rec['fa']:.4f} "
                  f"MI {rec['mi_raw_bits']:.3f}/{rec['mi_cal_splithalf_bits']:.3f}",
                  flush=True)
            if do_ldpc:
                y = {r: round(rec['ldpc_measured'][r]['yield'], 3)
                     for r in p5.RUNGS}
                print(f"      ldpc yields {y}", flush=True)
        report["footings"][tag] = frec
        print(f"[{tag}] 7-state cross-tile acc {acc7:.4f} "
              f"({time.time()-t0:.0f}s)", flush=True)
    report["runtime_s"] = round(time.time() - t0, 1)
    (OUT / "canon-p5.json").write_text(json.dumps(report, indent=1))
    print(f"-> {OUT / 'canon-p5.json'}", flush=True)


if __name__ == "__main__":
    main()

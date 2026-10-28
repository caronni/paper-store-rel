"""E004 analyzer: the M2 four-cell matrix, scored per tile on one sheet.

Reuses, verbatim where possible (house pattern, attribution in imports):
cal_core registration/patch machinery (002), cal_color aligned-density QDA
(002.0), analyze_overlap2 alphabet measurement (002.2), analyze_modprobe
fixed-rate dot decode (003.0), scanlab v4 decode (001.4), and the 003.0a
PAVA monotone LLR recalibration.

New here (the two things E004 exists to measure):
  * cross-tile-trained QDA for A3/A4 — train on the other 15 tiles of the
    class, predict the held-out tile; the honest number the QDA-fold-optimism
    caveat demands (same-fold numbers are also reported, comparable 002.2);
  * per-class position maps over the 8x8 balanced grid.

Usage (from experiments/004-finalists-checkerboard/):
    ../../env/bin/python analyze_e004.py ../../scans/finalists.png
Writes build/e004_report.json; prints the leaderboard vs the pre-registered
envelopes of experiments/004-finalists-checkerboard.md.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
for rel in ("002-calibration-page", "003-modulation-probes",
            "001-engine-characterization"):
    p = str(_HERE.parent / rel)
    if p not in sys.path:
        sys.path.insert(0, p)
sys.path.insert(0, str(_HERE.parents[1] / "src"))

import analyze_k4e2_context as k4  # noqa: E402  (PAVA recal, 003.0a)
import analyze_modprobe as amp  # noqa: E402     (fixed-rate dot decode, 003.0)
import analyze_overlap2 as ao2  # noqa: E402     (alphabet QDA wrapper, 002.2)
import cal_color as ccol  # noqa: E402           (aligned densities, QDA)
import cal_core as cc  # noqa: E402              (registration, patch views)
import scanlab  # noqa: E402                     (v4 decode, 001.4)

BUILD = _HERE / "build"
MANIFEST_PATH = BUILD / "e004_manifest.json"
GRID_N = 8
CELLS_MM2 = {"A3": (600 / 25.4 / 3) ** 2, "A4": (600 / 25.4 / 4) ** 2,
             "B1": (600 / 25.4 / 2) ** 2}
DOTS_MM2 = (600 / 25.4) ** 2
ENVELOPES = {
    "A3": "same-fold MI 1.33-1.63 b/cell",
    "A4": "same-fold MI 1.98-2.36 b/cell",
    "B1": "hard 10.5-12.5% | ctx 4.3-5.6% | recal MI 0.70-0.85 b/cell",
    "B2": "naive dot BER 12-15%",
}


def tiles_of(manifest: dict, cls: str) -> list[dict]:
    return [t for t in manifest["tiles"] if t["class"] == cls]


# ---------------------------------------------------------------------------
# rectangular tiles through the square-only v4 decoder: two overlapping
# squares stitched at the overlap midline (003's "decode_cells_v4_2squares"
# construction, generalized — each square gets its own dense warp)
# ---------------------------------------------------------------------------

def decode_rect_by_squares(scan: dict, e: dict, gt: np.ndarray, cell: int,
                           channel: str, **kw) -> dict:
    x, y, w, h = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
    assert h > w and (h - w) % cell == 0 and w % cell == 0, (e["name"], w, h)
    arr = cc._channel_f32(scan, channel)
    sq_t = {"name": e["name"] + "#top", "x_dots": x, "y_dots": y,
            "w_dots": w, "h_dots": w}
    sq_b = {"name": e["name"] + "#bot", "x_dots": x, "y_dots": y + h - w,
            "w_dots": w, "h_dots": w}
    out_t = scanlab.decode_cells(arr, scan["affine"], sq_t,
                                 gt[:w].astype(np.uint8), cell, **kw)
    out_b = scanlab.decode_cells(arr, scan["affine"], sq_b,
                                 gt[h - w:].astype(np.uint8), cell, **kw)
    split = (h // 2) // cell          # stitch at the overlap midline
    off = (h - w) // cell             # bottom square's row offset (cells)

    def stitch(key_t, key_b=None):
        a = np.asarray(key_t, np.float64)
        b = np.asarray(key_b if key_b is not None else key_t, np.float64)
        return np.concatenate([a[:split], b[split - off:]], axis=0)

    res = {"halves": (out_t, out_b),
           "means": stitch(out_t["means"], out_b["means"]),
           "err_map": stitch(out_t["err_map"], out_b["err_map"]) > 0.5}
    if kw.get("soft", True) and "soft" in out_t:
        res["llr_ctx"] = stitch(out_t["soft"]["llr_ctx"],
                                out_b["soft"]["llr_ctx"])
    return res


# ---------------------------------------------------------------------------
# Track B — clean-K tiles
# ---------------------------------------------------------------------------

def decode_b1_tile(scan: dict, name: str, frozen_map) -> dict:
    e = cc.entry(scan["manifest"], name)
    gt = cc.load_gt(e)
    out = decode_rect_by_squares(scan, e, gt, 2, "grey")
    gt_cells = gt[::2, ::2]
    llr = np.asarray(out["llr_ctx"], np.float64)
    err = (llr > 0) != gt_cells.astype(bool)

    # split-half PAVA recal (003.0a construction)
    iy, ix = np.mgrid[0:llr.shape[0], 0:llr.shape[1]]
    half = ((iy + ix) % 2).astype(bool)
    mis = []
    for train in (half, ~half):
        c, p = k4.fit_monotone_map(np.abs(llr[train]), err[train])
        mis.append(k4.mi_bits(k4.apply_map(llr[~train], c, p),
                              gt_cells[~train]))
    null = float(((llr > 0) != np.roll(gt_cells, 7, axis=0).astype(bool)).mean())
    rec = {
        "ber_hard": float(out["err_map"].mean()),
        "ber_ctx": float(err.mean()),
        "null_shifted_gt": null,
        "mi_recal_splithalf": float(np.mean(mis)),
    }
    if frozen_map is not None:
        rec["mi_recal_frozen_001_4"] = k4.mi_bits(
            k4.apply_map(llr, *frozen_map), gt_cells)
    return rec


def decode_b2_tile(scan: dict, name: str) -> dict:
    e = cc.entry(scan["manifest"], name)
    gt = cc.load_gt(e)
    p_ink = float(e["params"]["ink_fraction"])
    out = decode_rect_by_squares(scan, e, gt, 1, "grey",
                                 soft=False, diagnostics=False)
    bits = amp.fixed_rate_bits(out["means"], p_ink)
    gtb = gt.astype(bool)
    err = bits.astype(bool) != gtb
    h_src = float(e["params"]["sampler_entropy_bits_per_dot"])
    ber = float(err.mean())
    return {
        "ber_dot": ber,
        "miss": float(err[gtb].mean()), "fa": float(err[~gtb].mean()),
        "rate_proxy_b_per_dot": h_src * (1.0 - k4.h2(ber)),
        "sampler_entropy": h_src,
    }


# ---------------------------------------------------------------------------
# Track A — alphabet tiles: features once, then same-fold + cross-tile QDA
# ---------------------------------------------------------------------------

def tile_features(scan: dict, wm: dict, name: str,
                  planes: str) -> tuple[np.ndarray, np.ndarray]:
    """Per-cell density features, each plane aligned in its own channel by
    the 2-squares dense-warp decode (rect version of cal_color
    aligned_cell_densities — same white-model density transform)."""
    e0 = cc.entry(scan["manifest"], f"{name}_C")
    states = cc.load_gt_named(e0["params"]["states_gt"], BUILD).astype(np.int64)
    cell = int(e0["params"]["cell_dots"])
    feats = []
    for p in planes:
        e = cc.entry(scan["manifest"], f"{name}_{p}")
        ch = cc.reg_channel_for(scan, e)
        gt = cc.load_gt(e)
        out = decode_rect_by_squares(scan, e, gt, cell, ch,
                                     soft=False, diagnostics=False)
        means = out["means"]
        assert means.shape == states.shape, (name, p, means.shape, states.shape)
        nc_y, nc_x = means.shape
        xg, yg = np.meshgrid(
            e["x_dots"] + (np.arange(nc_x) + 0.5) * cell,
            e["y_dots"] + (np.arange(nc_y) + 0.5) * cell)
        white = cc.white_at(wm, xg, yg, ch)
        D = -np.log10(np.maximum(means, 1.0) / np.maximum(white, 1e-3))
        feats.append(D.ravel())
    return np.stack(feats, axis=1), states.ravel()


class GaussianQDA:
    """Full-covariance per-state Gaussian classifier, uniform priors (the
    alphabet is uniform by construction)."""

    def fit(self, X: np.ndarray, y: np.ndarray, n_states: int) -> "GaussianQDA":
        self.mu, self.icov, self.logdet = [], [], []
        for s in range(n_states):
            Z = X[y == s]
            mu = Z.mean(axis=0)
            cov = np.cov(Z.T) + 1e-9 * np.eye(X.shape[1])
            self.mu.append(mu)
            self.icov.append(np.linalg.inv(cov))
            self.logdet.append(np.linalg.slogdet(cov)[1])
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        ll = np.empty((X.shape[0], len(self.mu)))
        for s, (mu, ic, ld) in enumerate(zip(self.mu, self.icov, self.logdet)):
            d = X - mu
            ll[:, s] = -0.5 * (np.einsum("ij,jk,ik->i", d, ic, d) + ld)
        return np.argmax(ll, axis=1)


def cross_tile_qda(feats: list[tuple[np.ndarray, np.ndarray]],
                   n_states: int) -> dict:
    conf = np.zeros((n_states, n_states), np.int64)
    for hold in range(len(feats)):
        Xtr = np.concatenate([X for i, (X, _) in enumerate(feats) if i != hold])
        ytr = np.concatenate([y for i, (_, y) in enumerate(feats) if i != hold])
        Xte, yte = feats[hold]
        pred = GaussianQDA().fit(Xtr, ytr, n_states).predict(Xte)
        conf += ccol._confusion(yte, pred, n_states)
    n = conf.sum()
    return {"accuracy": float(np.trace(conf) / n),
            "mi_bits": float(ccol._mi_bits_from_counts(conf.astype(np.float64))),
            "confusion": conf.tolist()}


# ---------------------------------------------------------------------------

def position_map(manifest: dict, per_tile: dict, key: str) -> dict:
    by_row: dict[str, list] = {}
    by_col: dict[str, list] = {}
    for t in manifest["tiles"]:
        v = per_tile.get(t["name"], {}).get(key)
        if v is None:
            continue
        by_row.setdefault(t["row"], []).append(v)
        by_col.setdefault(t["col"], []).append(v)
    return {"by_row": {r: float(np.mean(v)) for r, v in sorted(by_row.items())},
            "by_col": {c: float(np.mean(v)) for c, v in sorted(by_col.items())}}


def main(scan_path: str) -> None:
    t0 = time.time()
    manifest = cc.load_manifest(MANIFEST_PATH)
    scan = cc.load_scan(scan_path)
    print(f"scan {Path(scan_path).name}: {scan.get('sha256', '?')}", flush=True)
    reg = cc.register(scan, manifest)
    coef = np.asarray(scan["affine"], np.float64)
    reg_scalars = {k: v for k, v in reg.items()
                   if isinstance(v, (int, float, str, bool))}
    print(f"registered: {reg_scalars}", flush=True)
    print(f"affine px/dot: x {coef[0]:.5f}, y {coef[4]:.5f}", flush=True)
    wm = cc.white_model(scan)

    report: dict = {"scan": Path(scan_path).name,
                    "scan_sha256": scan.get("sha256"),
                    "registration": reg_scalars,
                    "tiles": {}, "classes": {}}
    per_tile = report["tiles"]

    # frozen 001.4 cross-sheet recal map (003.0a transfer replication)
    frozen = None
    f = (_HERE.parent / "001-engine-characterization" / "build"
         / "analysis-test-scan-gridtest" / "encode_c2_v4_metrics.json")
    if f.exists():
        rel = json.loads(f.read_text())["v4"]["reliability_ctx"]
        centers = np.array([(b["llr_lo"] + b["llr_hi"]) / 2 for b in rel])
        pr = np.clip(k4.pava_nonincreasing(
            np.array([b["emp_err"] for b in rel]),
            np.array([max(b.get("n", 1), 1) for b in rel])), 1e-5, 0.5)
        frozen = (centers, pr)

    # -- Track B ------------------------------------------------------------
    for t in tiles_of(manifest, "B1"):
        per_tile[t["name"]] = decode_b1_tile(scan, t["name"], frozen)
        r = per_tile[t["name"]]
        print(f"{t['name']}: hard {r['ber_hard']:.4f} ctx {r['ber_ctx']:.4f} "
              f"recal {r['mi_recal_splithalf']:.3f}", flush=True)
    for t in tiles_of(manifest, "B2"):
        per_tile[t["name"]] = decode_b2_tile(scan, t["name"])
        r = per_tile[t["name"]]
        print(f"{t['name']}: dot BER {r['ber_dot']:.4f} "
              f"rate {r['rate_proxy_b_per_dot']:.4f} b/dot", flush=True)

    # -- Track A ------------------------------------------------------------
    for cls, planes, n_states in (("A3", "CMY", 7), ("A4", "CMYK", 8)):
        feats, same_fold = [], []
        for t in tiles_of(manifest, cls):
            X, y = tile_features(scan, wm, t["name"], planes)
            feats.append((X, y))
            res = ccol._gaussian_cv_classify(X, y, n_states)
            per_tile[t["name"]] = {"acc_samefold": res["accuracy"],
                                   "mi_samefold": res["mi_bits"]}
            same_fold.append(res["mi_bits"])
            print(f"{t['name']}: same-fold acc {res['accuracy']:.3f} "
                  f"MI {res['mi_bits']:.3f}", flush=True)
        ct = cross_tile_qda(feats, n_states)
        report["classes"][cls] = {
            "mi_samefold_mean": float(np.mean(same_fold)),
            "mi_samefold_range": [float(np.min(same_fold)),
                                  float(np.max(same_fold))],
            "cross_tile": ct,
        }
        print(f"{cls} CROSS-TILE: acc {ct['accuracy']:.3f} "
              f"MI {ct['mi_bits']:.3f}", flush=True)

    # -- summary ------------------------------------------------------------
    b1 = [per_tile[t["name"]] for t in tiles_of(manifest, "B1")]
    b2 = [per_tile[t["name"]] for t in tiles_of(manifest, "B2")]
    summary = {
        "A3": {"mi_samefold": report["classes"]["A3"]["mi_samefold_mean"],
               "mi_crosstile": report["classes"]["A3"]["cross_tile"]["mi_bits"],
               "b_mm2_crosstile": report["classes"]["A3"]["cross_tile"]["mi_bits"] * CELLS_MM2["A3"],
               "b_mm2_samefold": report["classes"]["A3"]["mi_samefold_mean"] * CELLS_MM2["A3"]},
        "A4": {"mi_samefold": report["classes"]["A4"]["mi_samefold_mean"],
               "mi_crosstile": report["classes"]["A4"]["cross_tile"]["mi_bits"],
               "b_mm2_crosstile": report["classes"]["A4"]["cross_tile"]["mi_bits"] * CELLS_MM2["A4"],
               "b_mm2_samefold": report["classes"]["A4"]["mi_samefold_mean"] * CELLS_MM2["A4"]},
        "B1": {"ber_hard_mean": float(np.mean([r["ber_hard"] for r in b1])),
               "ber_ctx_mean": float(np.mean([r["ber_ctx"] for r in b1])),
               "ber_ctx_range": [float(np.min([r["ber_ctx"] for r in b1])),
                                 float(np.max([r["ber_ctx"] for r in b1]))],
               "mi_recal_mean": float(np.mean([r["mi_recal_splithalf"] for r in b1])),
               "mi_recal_frozen_mean": float(np.mean(
                   [r.get("mi_recal_frozen_001_4", np.nan) for r in b1])),
               "b_mm2": float(np.mean([r["mi_recal_splithalf"] for r in b1])) * CELLS_MM2["B1"]},
        "B2": {"ber_dot_mean": float(np.mean([r["ber_dot"] for r in b2])),
               "rate_mean_b_per_dot": float(np.mean(
                   [r["rate_proxy_b_per_dot"] for r in b2])),
               "b_mm2": float(np.mean([r["rate_proxy_b_per_dot"] for r in b2])) * DOTS_MM2},
    }
    report["summary"] = summary
    report["position_maps"] = {
        "B1_ber_ctx": position_map(manifest, per_tile, "ber_ctx"),
        "B2_ber_dot": position_map(manifest, per_tile, "ber_dot"),
        "A_mi_samefold": position_map(manifest, per_tile, "mi_samefold"),
    }
    report["envelopes"] = ENVELOPES
    report["runtime_s"] = round(time.time() - t0, 1)
    (BUILD / "e004_report.json").write_text(json.dumps(report, indent=1))

    print("\n==== E004 leaderboard (this sheet, genie-synced) ====", flush=True)
    print(f"A3 7st-c3 : same-fold {summary['A3']['mi_samefold']:.3f} b/cell"
          f" = {summary['A3']['b_mm2_samefold']:.1f} b/mm2 | CROSS-TILE "
          f"{summary['A3']['mi_crosstile']:.3f} = "
          f"{summary['A3']['b_mm2_crosstile']:.1f} b/mm2   [{ENVELOPES['A3']}]")
    print(f"A4 {{7+K}}c4: same-fold {summary['A4']['mi_samefold']:.3f} b/cell"
          f" = {summary['A4']['b_mm2_samefold']:.1f} b/mm2 | CROSS-TILE "
          f"{summary['A4']['mi_crosstile']:.3f} = "
          f"{summary['A4']['b_mm2_crosstile']:.1f} b/mm2   [{ENVELOPES['A4']}]")
    print(f"B1 c2-K   : hard {summary['B1']['ber_hard_mean']:.4f} | ctx "
          f"{summary['B1']['ber_ctx_mean']:.4f} "
          f"({summary['B1']['ber_ctx_range'][0]:.4f}-"
          f"{summary['B1']['ber_ctx_range'][1]:.4f}) | recal MI "
          f"{summary['B1']['mi_recal_mean']:.3f} (frozen-map "
          f"{summary['B1']['mi_recal_frozen_mean']:.3f}) = "
          f"{summary['B1']['b_mm2']:.1f} b/mm2   [{ENVELOPES['B1']}]")
    print(f"B2 RLL    : dot BER {summary['B2']['ber_dot_mean']:.4f} | rate "
          f"{summary['B2']['rate_mean_b_per_dot']:.4f} b/dot = "
          f"{summary['B2']['b_mm2']:.1f} b/mm2   [{ENVELOPES['B2']}]")
    print(f"runtime {report['runtime_s']}s -> build/e004_report.json", flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../../scans/finalists.png")

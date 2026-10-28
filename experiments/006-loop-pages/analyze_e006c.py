"""006.2 — E006-C analyzer: the color loop page (7-state CMY alphabet, c3).

Registration = 4 chiral corners (affine, refine=False by design) + the 17
known K sync strips (strip_tracker: template xcorr, absolute anchors).
Per color scan, each of the 16 A3 payload bands yields per-cell features
X (n_cells, 4): strip-warp-sampled cell means in the plane channels
(C->r, M->g, Y->b) density-transformed against the white model, plus a
grey-channel feature on the same warp. GT (states npy) scores, never decodes.

Three classification columns per band:
  (1) BLIND-EM     — em_gaussian_uniform init at crosstalk-predicted
                     centroids (legal receiver knowledge, fully blind);
  (2) TRAIN-QDA    — GaussianQDA fit on the three manifest-flagged training
                     bands (0/7/15), predicting the other 13 (the loop-legal
                     protocol);
  (3) CROSS-QDA    — 16-fold train-on-15/test-on-1 (genie-training ref).
Accuracy + plug-in MI (cal_color) each; areal = MI x 62.0 b/mm2 (c3).

Multi-scan: per-cell FEATURE averaging over color scans [2], [2,3], [2,3,4],
columns (1) and (2) redone on the averaged features (the ladder).

CHANNEL-STATE RECORD (color toners very low at print time): ref-row and
canary solid densities per plane per scan (grey + color), plus per-band
per-state class-mean drift for the Y-bearing states (banding/starvation
check down the page).

Scans: 006col-scan-1-bw (grey: strips/canary/ref densities only),
-2-col and -3-col (color, placement identical to 1), -4-col (color,
180 deg rotated — chiral corners resolve orientation).

Writes build/e006c_report.json.
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
for rel in ("..", "../002-calibration-page", "../003-modulation-probes",
            "../001-engine-characterization",
            "../004-finalists-checkerboard"):
    p = str((_HERE / rel).resolve())
    if p not in sys.path:
        sys.path.insert(0, p)
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parents[1] / "src"))

import analyze_e004 as ae4  # noqa: E402  (GaussianQDA)
import analyze_modprobe as amp  # noqa: E402  (fixed_rate_bits — canaries)
import blind_alphabet as ba  # noqa: E402
import cal_color as ccol  # noqa: E402  (_confusion, _mi_bits_from_counts)
import cal_core as cc  # noqa: E402
import strip_tracker as st  # noqa: E402

BUILD = _HERE / "build"
SCANS_DIR = _HERE.parents[1] / "scans"
SCANS = {
    "s1grey": "006col-scan-1-bw.png",
    "s2col": "006col-scan-2-col.png",
    "s3col": "006col-scan-3-col.png",
    "s4col": "006col-scan-4-col.png",
}
COLOR_TAGS = ["s2col", "s3col", "s4col"]
CELL = 3
B_MM2_C3 = (600 / 25.4 / CELL) ** 2  # 62.0 b/mm2 per bit/cell
PLANE_CH = [("C", "r"), ("M", "g"), ("Y", "b")]
FEAT_CHANNELS = ["r", "g", "b", "grey"]
N_STATES = 7


# ---------------------------------------------------------------------------
# feature extraction
# ---------------------------------------------------------------------------

def cell_density(m: np.ndarray, wm: dict, e: dict, ch: str) -> np.ndarray:
    """White-model density transform of cell means at their layout centers
    (the tile_features pattern)."""
    ny, nx = m.shape
    xg, yg = np.meshgrid(e["x_dots"] + (np.arange(nx) + 0.5) * CELL,
                         e["y_dots"] + (np.arange(ny) + 0.5) * CELL)
    white = cc.white_at(wm, xg, yg, ch)
    return -np.log10(np.maximum(m, 1.0) / np.maximum(white, 1e-3))


def band_feature_stack(scan: dict, coef: np.ndarray, tr: dict, wm: dict,
                       manifest: dict, band_names: list[str]) -> dict:
    """X (n_cells, 4) per band, channel-by-channel so at most one r/g/b
    float32 copy is alive at a time (scans are 300 MB on disk)."""
    feats: dict[str, list[np.ndarray]] = {bn: [] for bn in band_names}
    for plane, ch in PLANE_CH:
        arr = cc._channel_f32(scan, ch)
        for bn in band_names:
            e = cc.entry(manifest, f"{bn}_{plane}")
            m = st.strip_cell_means(arr, coef, e, CELL, tr)
            feats[bn].append(
                cell_density(m, wm, e, ch).ravel().astype(np.float32))
        scan.get("_f32", {}).pop(ch, None)
        gc.collect()
    grey = cc._channel_f32(scan, "grey")
    for bn in band_names:
        e = cc.entry(manifest, f"{bn}_C")  # same rect for all planes
        m = st.strip_cell_means(grey, coef, e, CELL, tr)
        feats[bn].append(
            cell_density(m, wm, e, "grey").ravel().astype(np.float32))
    return {bn: np.stack(v, axis=1) for bn, v in feats.items()}


# ---------------------------------------------------------------------------
# channel-state record: solids + canaries
# ---------------------------------------------------------------------------

def measure_solids(scan: dict, wm: dict, manifest: dict,
                   inset_dots: int = 25) -> dict:
    """Median density of every unique solid rect (ref row, canary solids,
    canary paper gap) in every available channel — the low-toner record."""
    coef = np.asarray(scan["affine"], np.float64)
    chans = ("r", "g", "b", "grey") if scan["kind"] == "color" else ("grey",)
    rects: dict[str, dict] = {}
    for p in manifest["patches"]:
        if p["kind"] in ("ref_solid", "ref_solid_cmyk", "canary_solid"):
            rects.setdefault(p.get("composite_of") or p["name"], p)
    for e in manifest["infrastructure"]:
        if e["kind"] == "canary_gap":
            rects["canary_gap"] = e
    out = {}
    for key, e in rects.items():
        xs = np.arange(e["x_dots"] + inset_dots,
                       e["x_dots"] + e["w_dots"] - inset_dots, 0.5)
        ys = np.arange(e["y_dots"] + inset_dots,
                       e["y_dots"] + e["h_dots"] - inset_dots, 0.5)
        xg, yg = np.meshgrid(xs, ys)
        sx = coef[0] * xg + coef[1] * yg + coef[2]
        sy = coef[3] * xg + coef[4] * yg + coef[5]
        rec = {}
        for ch in chans:
            v = ndimage.map_coordinates(scan["channels"][ch], [sy, sx],
                                        order=1, mode="nearest",
                                        output=np.float32)
            white = float(np.mean(cc.white_at(wm, xg, yg, ch)))
            rec[ch] = round(-float(np.log10(
                max(float(np.median(v)), 1.0) / max(white, 1e-3))), 4)
        out[key] = rec
    return out


def measure_canaries(grey: np.ndarray, coef: np.ndarray, tr: dict,
                     manifest: dict) -> dict:
    out = {}
    e = cc.entry(manifest, "c/canary_b1")
    gt = cc.load_gt(e)
    gtc = gt[::2, ::2].astype(bool)
    m = st.strip_cell_means(grey, coef, e, 2, tr)
    out["canary_b1_ber_c2"] = float(
        (amp.fixed_rate_bits(m, 0.5).astype(bool) != gtc).mean())
    e = cc.entry(manifest, "c/canary_rll")
    gtb = cc.load_gt(e).astype(bool)
    m = st.strip_cell_means(grey, coef, e, 1, tr)
    bits = amp.fixed_rate_bits(m, float(e["params"]["ink_fraction"]))
    out["canary_rll_ber_dot"] = float((bits.astype(bool) != gtb).mean())
    return out


# ---------------------------------------------------------------------------
# per-scan processing (sequential, freed after)
# ---------------------------------------------------------------------------

def process_scan(tag: str, manifest: dict, strips: list[dict],
                 band_names: list[str]) -> tuple[dict, dict | None]:
    t0 = time.time()
    scan = cc.load_scan(SCANS_DIR / SCANS[tag], compute_sha256=False)
    # refine=False: E006 pages carry only 4 corner landmarks by design
    # (strips supersede the plus lattice; cal_core refinement needs >=6).
    reg = cc.register(scan, manifest, refine=False)
    coef = np.asarray(scan["affine"], np.float64)
    grey = cc._channel_f32(scan, "grey")
    out: dict = {"tag": tag, "kind": scan["kind"],
                 "reg": {k: v for k, v in reg.items()
                         if isinstance(v, (int, float, str, bool))}}

    tr = st.track_strips(grey, coef, strips)
    out["strip_lock_rate"] = float(np.isfinite(tr["dy"]).mean())
    out["strip_dy_span"] = [float(np.nanmin(tr["dy"])),
                            float(np.nanmax(tr["dy"]))]

    wm = cc.white_model(scan)
    out["solids_density"] = measure_solids(scan, wm, manifest)
    out["canary"] = measure_canaries(grey, coef, tr, manifest)

    X = None
    if scan["kind"] == "color":
        X = band_feature_stack(scan, coef, tr, wm, manifest, band_names)

    print(f"[{tag}] {scan['kind']} lock {out['strip_lock_rate']:.2f} "
          f"dy [{out['strip_dy_span'][0]:.1f},{out['strip_dy_span'][1]:.1f}] "
          f"canary b1 {out['canary']['canary_b1_ber_c2']:.4f} "
          f"rll {out['canary']['canary_rll_ber_dot']:.4f} "
          f"({time.time() - t0:.0f}s)", flush=True)
    scan.clear()
    gc.collect()
    return out, X


# ---------------------------------------------------------------------------
# classification columns
# ---------------------------------------------------------------------------

def score(y: np.ndarray, pred: np.ndarray) -> dict:
    conf = ccol._confusion(y, pred, N_STATES)
    return {"acc": float(np.trace(conf) / conf.sum()),
            "mi": float(ccol._mi_bits_from_counts(conf.astype(np.float64))),
            "_conf": conf}


def classify(X: dict, states: dict, band_names: list[str],
             train_bands: list[str], state_names: list[str],
             with_cross: bool) -> dict:
    """Columns 1-3 on one feature set. Returns per-band dicts + pooled
    confusions + GT class means (7 x 4) per band."""
    mu0 = ba.predicted_centroids(state_names, FEAT_CHANNELS)
    res: dict = {"bands": {}, "pooled_conf": {}}
    pooled = {"blind": np.zeros((N_STATES, N_STATES), np.int64),
              "train": np.zeros((N_STATES, N_STATES), np.int64),
              "cross": np.zeros((N_STATES, N_STATES), np.int64)}

    qda = ae4.GaussianQDA().fit(
        np.concatenate([X[b] for b in train_bands]).astype(np.float64),
        np.concatenate([states[b] for b in train_bands]), N_STATES)

    for bn in band_names:
        y = states[bn]
        Xb = X[bn].astype(np.float64)
        rec: dict = {"train_band": bn in train_bands}

        em = ba.em_gaussian_uniform(Xb, mu0.copy())
        s = score(y, em["pred"])
        pooled["blind"] += s.pop("_conf")
        rec["blind"] = s

        s = score(y, qda.predict(Xb))
        conf = s.pop("_conf")
        if bn not in train_bands:
            pooled["train"] += conf
        rec["train"] = s

        if with_cross:
            others = [b for b in band_names if b != bn]
            q = ae4.GaussianQDA().fit(
                np.concatenate([X[b] for b in others]).astype(np.float64),
                np.concatenate([states[b] for b in others]), N_STATES)
            s = score(y, q.predict(Xb))
            pooled["cross"] += s.pop("_conf")
            rec["cross"] = s

        rec["class_means"] = [[round(float(Xb[y == c, f].mean()), 4)
                               for f in range(len(FEAT_CHANNELS))]
                              for c in range(N_STATES)]
        res["bands"][bn] = rec
    res["pooled_conf"] = {k: v.tolist() for k, v in pooled.items()
                          if v.sum() > 0}
    return res


def page_means(cls: dict, band_names: list[str],
               test_bands: list[str]) -> dict:
    b = cls["bands"]
    out = {
        "blind_acc_16": float(np.mean([b[n]["blind"]["acc"] for n in band_names])),
        "blind_mi_16": float(np.mean([b[n]["blind"]["mi"] for n in band_names])),
        "blind_mi_13": float(np.mean([b[n]["blind"]["mi"] for n in test_bands])),
        "train_acc_13": float(np.mean([b[n]["train"]["acc"] for n in test_bands])),
        "train_mi_13": float(np.mean([b[n]["train"]["mi"] for n in test_bands])),
    }
    if "cross" in b[band_names[0]]:
        out["cross_acc_16"] = float(np.mean([b[n]["cross"]["acc"]
                                             for n in band_names]))
        out["cross_mi_16"] = float(np.mean([b[n]["cross"]["mi"]
                                            for n in band_names]))
        out["cross_mi_13"] = float(np.mean([b[n]["cross"]["mi"]
                                            for n in test_bands]))
        out["cross_acc_13"] = float(np.mean([b[n]["cross"]["acc"]
                                             for n in test_bands]))
    out["train_b_mm2"] = out["train_mi_13"] * B_MM2_C3
    out["blind_b_mm2"] = out["blind_mi_16"] * B_MM2_C3
    return out


# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()
    manifest = cc.load_manifest(BUILD / "e006c_manifest.json")
    band_meta = [b for b in manifest["bands"] if b["kind"] == "state_field"]
    band_names = [b["name"] for b in band_meta]
    train_bands = [b["name"] for b in band_meta
                   if b["params"].get("purpose") == "training"]
    test_bands = [n for n in band_names if n not in train_bands]
    state_names = band_meta[0]["params"]["state_names"]
    states = {}
    for b in band_meta:
        y = cc.load_gt_named(b["params"]["states_gt"], BUILD)
        states[b["name"]] = y.ravel().astype(np.int64)

    strips = []
    for p in manifest["patches"]:
        if p["kind"] == "sync_strip":
            strips.append({**{k: p[k] for k in
                              ("x_dots", "y_dots", "w_dots", "h_dots")},
                           "gt": cc.load_gt(p)})

    scan_out: dict = {}
    feats: dict = {}
    for tag in SCANS:
        rec, X = process_scan(tag, manifest, strips, band_names)
        scan_out[tag] = rec
        if X is not None:
            feats[tag] = X

    # per-scan classification columns (with genie cross-band)
    per_scan = {}
    for tag in COLOR_TAGS:
        tc = time.time()
        per_scan[tag] = classify(feats[tag], states, band_names,
                                 train_bands, state_names, with_cross=True)
        pm = page_means(per_scan[tag], band_names, test_bands)
        per_scan[tag]["page_means"] = pm
        print(f"[{tag}] blind {pm['blind_acc_16']:.4f}/{pm['blind_mi_16']:.3f} "
              f"train(13) {pm['train_acc_13']:.4f}/{pm['train_mi_13']:.3f} "
              f"cross(13) {pm['cross_acc_13']:.4f}/{pm['cross_mi_13']:.3f} "
              f"({time.time() - tc:.0f}s)", flush=True)

    # multi-scan feature-averaged ladder, columns (1) and (2)
    ladder = {}
    for subset in ([COLOR_TAGS[0]], COLOR_TAGS[:2], COLOR_TAGS):
        key = "+".join(subset)
        if len(subset) == 1:
            cls = per_scan[subset[0]]  # identical features — reuse
        else:
            Xavg = {bn: np.mean([feats[t][bn].astype(np.float64)
                                 for t in subset], axis=0)
                    for bn in band_names}
            cls = classify(Xavg, states, band_names, train_bands,
                           state_names, with_cross=False)
            del Xavg
            gc.collect()
        ladder[key] = page_means(cls, band_names, test_bands)
        if len(subset) > 1:
            ladder[key]["bands"] = {
                bn: {k: v for k, v in cls["bands"][bn].items()
                     if k in ("blind", "train", "train_band")}
                for bn in band_names}

    # gaps on the primary scan (13 test bands, apples-to-apples)
    b2 = per_scan["s2col"]["bands"]
    gap_train_genie = {
        "d_acc_pp": float(np.mean([100 * (b2[n]["cross"]["acc"]
                                          - b2[n]["train"]["acc"])
                                   for n in test_bands])),
        "d_mi": float(np.mean([b2[n]["cross"]["mi"] - b2[n]["train"]["mi"]
                               for n in test_bands]))}
    gap_blind = {
        "d_acc_pp": float(np.mean([100 * (b2[n]["train"]["acc"]
                                          - b2[n]["blind"]["acc"])
                                   for n in test_bands])),
        "d_mi": float(np.mean([b2[n]["train"]["mi"] - b2[n]["blind"]["mi"]
                               for n in test_bands]))}

    # Y-bearing-state class-mean drift (b-channel density, feature idx 2)
    y_idx = {s: state_names.index(s) for s in ("W", "Y", "CY", "MY")}
    y_drift = {}
    for tag in COLOR_TAGS:
        y_drift[tag] = {s: [per_scan[tag]["bands"][bn]["class_means"][i][2]
                            for bn in band_names]
                        for s, i in y_idx.items()}

    report = {
        "experiment": "006.2 e006c",
        "cell_dots": CELL, "n_states": N_STATES,
        "state_names": state_names,
        "band_names": band_names, "train_bands": train_bands,
        "areal_b_mm2_per_bit": B_MM2_C3,
        "scans": scan_out,
        "per_scan": {t: {"page_means": per_scan[t]["page_means"],
                         "pooled_conf": per_scan[t]["pooled_conf"],
                         "bands": per_scan[t]["bands"]}
                     for t in COLOR_TAGS},
        "gap_train_vs_genie_s2": gap_train_genie,
        "gap_blind_vs_train_s2": gap_blind,
        "multi_scan_ladder": ladder,
        "y_state_Db_by_band": y_drift,
        "runtime_s": round(time.time() - t0, 1),
    }
    (BUILD / "e006c_report.json").write_text(json.dumps(report, indent=1))

    # ------------------------------------------------------------------
    print("\n==== E006-C COLOR LOOP SUMMARY ====", flush=True)
    print("scan            lock  dy_span            canary_b1  canary_rll")
    for tag, r in scan_out.items():
        print(f"{tag:14s}  {r['strip_lock_rate']:.2f}  "
              f"[{r['strip_dy_span'][0]:+5.1f},{r['strip_dy_span'][1]:+5.1f}]"
              f"      {r['canary']['canary_b1_ber_c2']:.4f}     "
              f"{r['canary']['canary_rll_ber_dot']:.4f}")

    print("\n-- solid densities (own channel), the low-toner record --")
    own = {"K": "grey", "C": "r", "M": "g", "Y": "b"}
    keys = ["ref_clean_K", "ref_clean_C", "ref_clean_M", "ref_clean_Y",
            "ref_cmyk_C", "ref_cmyk_M", "ref_cmyk_Y", "ref_cmyk_CM",
            "ref_cmyk_CY", "ref_cmyk_MY", "c/canary_solid_K",
            "c/canary_solid_C", "c/canary_solid_M", "c/canary_solid_Y",
            "canary_gap"]
    hdr = "solid              " + "".join(f"{t:>22s}" for t in SCANS)
    print(hdr)
    for k in keys:
        row = f"{k:18s}"
        for tag in SCANS:
            d = scan_out[tag]["solids_density"].get(k, {})
            if scan_out[tag]["kind"] != "color":
                chs = ["grey"]
            else:
                planes = [p for p in "KCMY" if p in k.split("_")[-1]]
                chs = [own[p] for p in planes] or ["grey"]
            vals = "/".join(f"{d[c]:.3f}" if c in d else "-" for c in chs)
            row += f"{vals:>22s}"
        print(row)

    print("\n-- per-scan columns (acc / MI bits; train+blind_13 exclude "
          "training bands) --")
    for tag in COLOR_TAGS:
        pm = per_scan[tag]["page_means"]
        print(f"{tag}: BLIND-EM {pm['blind_acc_16']:.4f}/{pm['blind_mi_16']:.3f} "
              f"| TRAIN-QDA(13) {pm['train_acc_13']:.4f}/{pm['train_mi_13']:.3f} "
              f"= {pm['train_b_mm2']:.1f} b/mm2 "
              f"| CROSS-QDA(13) {pm['cross_acc_13']:.4f}/{pm['cross_mi_13']:.3f}")

    tmis = {n: b2[n]["train"]["mi"] for n in test_bands}
    best = max(tmis, key=tmis.get)
    worst = min(tmis, key=tmis.get)
    print(f"\ns2 TRAIN-QDA best band  {best}: MI {tmis[best]:.3f} "
          f"acc {b2[best]['train']['acc']:.4f}")
    print(f"s2 TRAIN-QDA worst band {worst}: MI {tmis[worst]:.3f} "
          f"acc {b2[worst]['train']['acc']:.4f}")
    print(f"train-vs-genie gap (s2, 13 bands): "
          f"{gap_train_genie['d_acc_pp']:+.2f} pp acc, "
          f"{gap_train_genie['d_mi']:+.4f} MI (genie minus train)")
    print(f"blind-EM gap      (s2, 13 bands): "
          f"{gap_blind['d_acc_pp']:+.2f} pp acc, "
          f"{gap_blind['d_mi']:+.4f} MI (train minus blind)")

    print("\n-- multi-scan feature-averaged ladder --")
    for key, pm in ladder.items():
        print(f"[{key}]: BLIND {pm['blind_acc_16']:.4f}/{pm['blind_mi_16']:.3f} "
              f"= {pm['blind_b_mm2']:.1f} b/mm2 | TRAIN(13) "
              f"{pm['train_acc_13']:.4f}/{pm['train_mi_13']:.3f} "
              f"= {pm['train_b_mm2']:.1f} b/mm2")

    print("\n-- Y-bearing state class-mean D_b by band (s2col; "
          "W = paper ref) --")
    print("band  " + "".join(f"{s:>8s}" for s in ("W", "Y", "CY", "MY")))
    for i, bn in enumerate(band_names):
        print(f"{i:4d}  " + "".join(
            f"{y_drift['s2col'][s][i]:8.3f}" for s in ("W", "Y", "CY", "MY")))
    for s in ("Y", "CY", "MY"):
        v = np.array(y_drift["s2col"][s])
        print(f"{s}: D_b top-band {v[0]:.3f} bottom-band {v[-1]:.3f} "
              f"drift {v[-1] - v[0]:+.3f} (min {v.min():.3f} @ band "
              f"{int(v.argmin())})")

    print(f"\nruntime {report['runtime_s']}s -> build/e006c_report.json",
          flush=True)


if __name__ == "__main__":
    main()

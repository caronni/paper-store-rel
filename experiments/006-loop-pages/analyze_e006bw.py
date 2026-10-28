"""006.1 — E006-BW analyzer: the first end-to-end LEGAL layer-1 pipeline.

Registration = 4 chiral corners (affine) + the 17 known sync strips
(strip_tracker: template xcorr, absolute anchors, no integer ambiguity).
Detection = blind throughout (fixed-rate at construction priors; the 16-
context detector on strip-tracked cell means; frozen 001.4 PAVA recal map).
Ground truth scores, never decodes. The GENIE column (decode_rect_by_squares)
is computed per band as the comparison — the strip-vs-genie gap IS the
legality result.

Scans: 006bw-scan-1-color (color pass), -2-bw and -3-bw (grey, placement
identical to 1), -4-bw (grey, re-placed). The unmoved 2-vs-3 pair isolates
pure per-scan-pass noise (sensor + fresh transport steps, zero placement
delta). Multi-scan combining per 004.0b.

Writes build/e006bw_report.json.
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

import analyze_e004 as ae4  # noqa: E402  (decode_rect_by_squares = genie ref)
import analyze_k4e2_context as k4  # noqa: E402  (PAVA recal)
import analyze_modprobe as amp  # noqa: E402  (fixed_rate_bits)
import cal_core as cc  # noqa: E402
import scanlab  # noqa: E402  (fit_gmm_z / llr_field / context_detect — blind)
import strip_tracker as st  # noqa: E402

BUILD = _HERE / "build"
SCANS_DIR = _HERE.parents[1] / "scans"
SCANS = {
    "s1col": "006bw-scan-1-color.png",
    "s2bw": "006bw-scan-2-bw.png",
    "s3bw": "006bw-scan-3-bw.png",
    "s4bw": "006bw-scan-4-bw.png",
}
CELLS_MM2_C2 = (600 / 25.4 / 2) ** 2
DOTS_MM2 = (600 / 25.4) ** 2


def blind_ctx_llr(means: np.ndarray) -> np.ndarray:
    """Blind soft stage on strip-tracked cell means: robust z-normalization,
    2-GMM (weights pinned 0.5), global LLRs, 16-context detector — the
    scanlab blind machinery applied outside decode_cells."""
    m = np.asarray(means, np.float64)
    lo, hi = np.quantile(m, (0.02, 0.98))
    z = (hi - m) / max(hi - lo, 1e-6)          # ~0 white, ~1 ink
    gmm = scanlab.fit_gmm_z(z)
    llr = scanlab.llr_field(z, gmm)
    return np.asarray(scanlab.context_detect(z, llr, gmm), np.float64)


def frozen_recal_map():
    f = (_HERE.parent / "001-engine-characterization" / "build"
         / "analysis-test-scan-gridtest" / "encode_c2_v4_metrics.json")
    rel = json.loads(f.read_text())["v4"]["reliability_ctx"]
    centers = np.array([(b["llr_lo"] + b["llr_hi"]) / 2 for b in rel])
    p = np.clip(k4.pava_nonincreasing(
        np.array([b["emp_err"] for b in rel]),
        np.array([max(b.get("n", 1), 1) for b in rel])), 1e-5, 0.5)
    return centers, p


def rect_cell_means(arr, coef, e, cw, ch, tr):
    """strip_cell_means generalized to rectangular cells (aniso probes)."""
    ny, nx = e["h_dots"] // ch, e["w_dots"] // cw
    yc = e["y_dots"] + (np.arange(ny) + 0.5) * ch
    xc = e["x_dots"] + (np.arange(nx) + 0.5) * cw
    dy, dx = st.offset_at(tr, yc, xc)
    yy = yc[:, None] + dy
    xx = xc[None, :] + dx
    out = np.zeros((ny, nx))
    for oy in (-0.25, 0.25):
        for ox in (-0.25, 0.25):
            xs = xx + ox * cw
            ys = yy + oy * ch
            sx = coef[0] * xs + coef[1] * ys + coef[2]
            sy = coef[3] * xs + coef[4] * ys + coef[5]
            out += ndimage.map_coordinates(arr, [sy, sx], order=1,
                                           mode="nearest")
    return out / 4.0


def process_scan(tag: str, manifest: dict, frozen) -> dict:
    scan = cc.load_scan(SCANS_DIR / SCANS[tag], compute_sha256=False)
    # refine=False: E006 pages carry only 4 corner landmarks by design
    # (strips supersede the plus lattice); cal_core's refinement pass
    # requires >=6. The corner-blob affine (~1.4 px rms) is exactly the
    # coarse start the strip tracker was built to take over from.
    reg = cc.register(scan, manifest, refine=False)
    coef = np.asarray(scan["affine"], np.float64)
    arr = cc._channel_f32(scan, "grey")
    out: dict = {"tag": tag,
                 "reg": {k: v for k, v in reg.items()
                         if isinstance(v, (int, float, str, bool))}}

    strips = []
    for p in manifest["patches"]:
        if p["kind"] == "sync_strip":
            strips.append({**{k: p[k] for k in
                              ("x_dots", "y_dots", "w_dots", "h_dots")},
                           "gt": cc.load_gt(p)})
    tr = st.track_strips(arr, coef, strips)
    out["strip_lock_rate"] = float(np.isfinite(tr["dy"]).mean())
    out["strip_dy_span"] = [float(np.nanmin(tr["dy"])),
                            float(np.nanmax(tr["dy"]))]

    bands: dict = {}
    for p in manifest["patches"]:
        kind = p.get("kind", "")
        name = p["name"]
        prm = p.get("params", {})
        if kind == "encoding_patch" and name.startswith("bw/band"):
            gt = cc.load_gt(p)
            gtc = gt[::2, ::2].astype(bool)
            m = st.strip_cell_means(arr, coef, p, 2, tr)
            llr = blind_ctx_llr(m)
            err = (llr > 0) != gtc
            rec = {"kind": "b1",
                   "ber_hard": float((amp.fixed_rate_bits(m, 0.5).astype(bool)
                                      != gtc).mean()),
                   "ber_ctx": float(err.mean()),
                   "mi_recal_frozen": k4.mi_bits(
                       k4.apply_map(llr, *frozen), gtc),
                   "llr": llr.astype(np.float32)}
            bands[name] = rec
        elif kind == "constrained_field" and name.startswith(("bw/rll",
                                                              "bw/i3w3")):
            gt = cc.load_gt(p)
            p_ink = float(prm["ink_fraction"])
            m = st.strip_cell_means(arr, coef, p, 1, tr)
            bits = amp.fixed_rate_bits(m, p_ink)
            gtb = gt.astype(bool)
            err = bits.astype(bool) != gtb
            resid = m - ndimage.median_filter(m, size=31, mode="nearest")
            mad = float(np.median(np.abs(resid - np.median(resid)))) + 1e-9
            bands[name] = {"kind": "rll", "ber_dot": float(err.mean()),
                           "miss": float(err[gtb].mean()),
                           "fa": float(err[~gtb].mean()),
                           "h_src": float(prm["sampler_entropy_bits_per_dot"]),
                           "resid_norm": (resid / mad).astype(np.float32)}
        elif kind in ("encoding_patch_fill75", "aniso_cell_field",
                      "grey3_field"):
            gt = cc.load_gt(p)
            if kind == "encoding_patch_fill75":
                # decode at CELL level against the cell decision (ink cells
                # are 3-of-4 dots; cell GT = any-ink per 2x2 block)
                gtc = (gt.reshape(gt.shape[0] // 2, 2, -1, 2)
                       .max(axis=(1, 3))).astype(bool)
                m = st.strip_cell_means(arr, coef, p, 2, tr)
                bits = amp.fixed_rate_bits(m, 0.5)
                err = bits.astype(bool) != gtc
                bands[name] = {"kind": "fill75",
                               "ber_cell": float(err.mean()),
                               "fa": float(err[~gtc].mean()),
                               "miss": float(err[gtc].mean())}
            elif kind == "aniso_cell_field":
                cw = int(prm["cell_w_dots"])
                ch = int(prm["cell_h_dots"])
                gtc = (gt.reshape(gt.shape[0] // ch, ch, -1, cw)
                       .max(axis=(1, 3))).astype(bool)
                m = rect_cell_means(arr, coef, p, cw, ch, tr)
                bits = amp.fixed_rate_bits(m, 0.5)
                bands[name] = {"kind": "aniso", "cell": f"{cw}x{ch}",
                               "ber_cell": float((bits.astype(bool)
                                                  != gtc).mean())}
            else:  # grey3
                cell = int(prm.get("cell_dots", 3))
                lv_rel = prm.get("levels_gt")
                lv = cc.load_gt_named(lv_rel, BUILD) if lv_rel else None
                m = st.strip_cell_means(arr, coef, p, cell, tr)
                if lv is None or lv.shape != m.shape:
                    bands[name] = {"kind": "grey3",
                                   "error": "levels gt missing/mismatch"}
                    continue
                q = np.quantile(m, (1 / 3, 2 / 3))
                pred = np.digitize(-m, np.sort(-q))  # dark=2, mid=1, light=0
                acc = float((pred == lv).mean())
                conf = np.zeros((3, 3))
                for a in range(3):
                    for b in range(3):
                        conf[a, b] = int(((lv == a) & (pred == b)).sum())
                import cal_color as ccol
                mi = float(ccol._mi_bits_from_counts(conf + 1e-9))
                bands[name] = {"kind": "grey3", "cell": cell,
                               "acc": acc, "mi_bits": mi,
                               "level_means": [float(m[lv == i].mean())
                                               for i in range(3)]}
    out["bands"] = bands
    b1 = [v for v in bands.values() if v["kind"] == "b1"]
    print(f"[{tag}] lock {out['strip_lock_rate']:.2f} "
          f"dy span [{out['strip_dy_span'][0]:.1f},{out['strip_dy_span'][1]:.1f}] | "
          f"B1 ctx {np.mean([v['ber_ctx'] for v in b1]):.4f} recal(frozen) "
          f"{np.mean([v['mi_recal_frozen'] for v in b1]):.3f} | "
          f"rll {np.mean([v['ber_dot'] for v in bands.values() if v['kind'] == 'rll' and 'i3w3' not in str(v)]):.4f}",
          flush=True)
    scan.clear()
    gc.collect()
    return out


def genie_band_wide(scan: dict, e: dict, gt: np.ndarray,
                    cell: int) -> np.ndarray:
    """Genie decode of a WIDE band (w >> h): horizontal tiling of square
    decode_cells sub-patches (each with its own GT-templated dense warp),
    llr_ctx stitched column-wise; the last square overlaps and contributes
    only its tail columns."""
    arr = cc._channel_f32(scan, "grey")
    s = e["h_dots"]
    xs = list(range(0, e["w_dots"] - s + 1, s))
    if xs[-1] != e["w_dots"] - s:
        xs.append(e["w_dots"] - s)
    n_cols = e["w_dots"] // cell
    llr = np.zeros((s // cell, n_cols))
    done = 0
    import scanlab as _sl
    for x0 in xs:
        sq = {"name": e["name"] + f"#x{x0}", "x_dots": e["x_dots"] + x0,
              "y_dots": e["y_dots"], "w_dots": s, "h_dots": s}
        out = _sl.decode_cells(arr, scan["affine"], sq,
                               gt[:, x0:x0 + s].astype(np.uint8), cell,
                               soft=True, diagnostics=False)
        part = np.asarray(out["soft"]["llr_ctx"], np.float64)
        c0 = x0 // cell
        c1 = c0 + s // cell
        start = max(done, c0)
        llr[:, start:c1] = part[:, start - c0:]
        done = c1
    return llr


def genie_reference(manifest: dict) -> dict:
    """Genie-warp comparison on scan 2 (grey, primary) — B1 bands only."""
    scan = cc.load_scan(SCANS_DIR / SCANS["s2bw"], compute_sha256=False)
    cc.register(scan, manifest, refine=False)
    ref = {}
    for p in manifest["patches"]:
        if p["kind"] == "encoding_patch" and p["name"].startswith("bw/band"):
            gt = cc.load_gt(p)
            llr = genie_band_wide(scan, p, gt, 2)
            gtc = gt[::2, ::2].astype(bool)
            ref[p["name"]] = {"ber_ctx": float(((llr > 0) != gtc).mean())}
    scan.clear()
    gc.collect()
    return ref


def main() -> None:
    t0 = time.time()
    manifest = cc.load_manifest(BUILD / "e006bw_manifest.json")
    frozen = frozen_recal_map()
    results = {tag: process_scan(tag, manifest, frozen) for tag in SCANS}
    genie = genie_reference(manifest)

    report: dict = {"scans": {t: {k: v for k, v in r.items() if k != "bands"}
                              for t, r in results.items()},
                    "genie_b1_s2": genie}

    # per-band tables + strip-vs-genie gap on the primary grey scan
    b1_names = sorted(n for n in results["s2bw"]["bands"]
                      if results["s2bw"]["bands"][n]["kind"] == "b1")
    report["b1_strip_vs_genie_s2"] = {
        n: {"strip_ctx": results["s2bw"]["bands"][n]["ber_ctx"],
            "genie_ctx": genie[n]["ber_ctx"],
            "gap_pp": 100 * (results["s2bw"]["bands"][n]["ber_ctx"]
                             - genie[n]["ber_ctx"])}
        for n in b1_names}

    # multi-scan combining (grey scans, then + color)
    combos = [["s2bw"], ["s2bw", "s3bw"], ["s2bw", "s3bw", "s4bw"],
              ["s2bw", "s3bw", "s4bw", "s1col"]]
    comb_out = {}
    for subset in combos:
        bers, mis = [], []
        for n in b1_names:
            tot = np.sum([results[s]["bands"][n]["llr"].astype(np.float64)
                          for s in subset], axis=0)
            gt = cc.load_gt(cc.entry_by_name(manifest, n)
                            if hasattr(cc, "entry_by_name") else
                            next(p for p in manifest["patches"]
                                 if p["name"] == n))
            gtc = gt[::2, ::2].astype(bool)
            err = (tot > 0) != gtc
            bers.append(float(err.mean()))
            iy, ix = np.mgrid[0:tot.shape[0], 0:tot.shape[1]]
            half = ((iy + ix) % 2).astype(bool)
            ms = []
            for train in (half, ~half):
                c, pp = k4.fit_monotone_map(np.abs(tot[train]), err[train])
                ms.append(k4.mi_bits(k4.apply_map(tot[~train], c, pp),
                                     gtc[~train]))
            mis.append(float(np.mean(ms)))
        rll_bers = []
        for n in [n for n in results["s2bw"]["bands"]
                  if results["s2bw"]["bands"][n]["kind"] == "rll"
                  and n.startswith("bw/rll")]:
            avg = np.mean([results[s]["bands"][n]["resid_norm"]
                           .astype(np.float64) for s in subset], axis=0)
            e = next(p for p in manifest["patches"] if p["name"] == n)
            gt = cc.load_gt(e)
            thr = np.quantile(avg, float(e["params"]["ink_fraction"]))
            rll_bers.append(float((((avg < thr)) != gt.astype(bool)).mean()))
        comb_out["+".join(subset)] = {
            "b1_ctx_mean": float(np.mean(bers)),
            "b1_mi_recal_mean": float(np.mean(mis)),
            "b1_b_mm2": float(np.mean(mis)) * CELLS_MM2_C2,
            "rll_ber_mean": float(np.mean(rll_bers)),
        }
    report["combining"] = comb_out

    # probes (primary scan) + strip health + unmoved-pair note
    report["probes_s2"] = {n: {k: v for k, v in r.items()
                               if k not in ("llr", "resid_norm")}
                           for n, r in results["s2bw"]["bands"].items()
                           if r["kind"] in ("rll", "fill75", "aniso", "grey3")
                           and not n.startswith("bw/rll")}
    report["b1_bands_s2"] = {n: {k: v for k, v in r.items() if k != "llr"}
                             for n, r in results["s2bw"]["bands"].items()
                             if r["kind"] == "b1"}
    report["runtime_s"] = round(time.time() - t0, 1)
    (BUILD / "e006bw_report.json").write_text(json.dumps(report, indent=1))

    print("\n==== E006-BW LAYER-1 LEGAL SUMMARY ====", flush=True)
    gaps = [v["gap_pp"] for v in report["b1_strip_vs_genie_s2"].values()]
    print(f"strip-vs-genie gap (B1, s2): mean {np.mean(gaps):+.2f} pp, "
          f"range [{min(gaps):+.2f}, {max(gaps):+.2f}]")
    for k, v in comb_out.items():
        print(f"COMBINE [{k}]: B1 ctx {v['b1_ctx_mean']:.4f} recal MI "
              f"{v['b1_mi_recal_mean']:.3f} = {v['b1_b_mm2']:.1f} b/mm2 | "
              f"RLL {v['rll_ber_mean']:.4f}")
    for n, r in sorted(report["probes_s2"].items()):
        print(f"probe {n}: { {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k != 'kind'} }")
    print(f"runtime {report['runtime_s']}s -> build/e006bw_report.json",
          flush=True)


if __name__ == "__main__":
    main()

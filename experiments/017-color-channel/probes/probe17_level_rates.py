"""P5-level-rates probe: per-LEVEL (C/M/Y presence) bit rates from e004 A3 GT.

Measures, on REAL scans (home M281 finalists + AltaLink xerox-e004), with the
e004 cross-tile QDA (the legal footing, machinery reused verbatim from
analyze_e004):
  * per-level hard bit BER (posterior-marginal decision), miss/fa, per-tile
    worst case;
  * per-level SOFT bit MI: raw QDA-posterior LLR and split-half
    PAVA-calibrated (003.0a construction, k4 machinery);
  * per-level LDPC ladder viability: measured per-cell calibrated
    LLR-toward-truth overlaid on real ladder codewords (all-zeros codeword,
    channel-symmetry overlay), decoded per rung {r0550..r0850} in 4096-cell
    raster blocks;
  * "Canon-halves" ESTIMATE: same overlay with a seeded half of the measured
    error cells un-flipped (magnitudes re-calibrated), per the 014.2-measured
    c2 improvement expectation. Labeled ESTIMATE.

Footing caveats (recorded in the JSON): e004 A3 is the 7-STATE alphabet
{W,C,M,Y,CM,CY,MY} — level-bit priors are 3/7 vs 4/7 and the CMY triple
stack is UNMEASURED; warp is genie-synced (2-squares dense warp); one
sheet/day per engine.

Usage:
  env/bin/python experiments/017-color-channel/probes/probe17_level_rates.py \\
      <scan> [...]
The run of record read scans/finalists.png + scans/xerox-e004-finalists-hp-scan.png
(evidence archive). Writes experiments/017-color-channel/build/
probe17_level_rates_report.json (the record is the copy beside this file).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
E004 = REPO / "experiments" / "004-finalists-checkerboard"
for rel in (E004, REPO / "experiments" / "002-calibration-page",
            REPO / "experiments" / "003-modulation-probes",
            REPO / "experiments" / "001-engine-characterization",
            REPO / "src"):
    if str(rel) not in sys.path:
        sys.path.insert(0, str(rel))

import analyze_e004 as ae  # noqa: E402  (tile_features, GaussianQDA, BUILD)
import analyze_k4e2_context as k4  # noqa: E402  (PAVA recal + mi_bits)
import cal_core as cc  # noqa: E402
from paperholo import ldpc  # noqa: E402

STATES7 = ("W", "C", "M", "Y", "CM", "CY", "MY")
LEVELS = "CMY"
MEMBER = {p: np.array([int(p in s) for s in STATES7], np.uint8) for p in LEVELS}
CELLS_MM2_C3 = (600 / 25.4 / 3) ** 2          # 61.98 cells/mm2
RUNGS = list(ldpc.LDPC_LADDER)                 # r0550..r0850
POST_CLIP = 1e-9


def qda_posterior_llrs(model: ae.GaussianQDA, X: np.ndarray) -> np.ndarray:
    """Per-level bit LLR (house sign: positive = bit 1 = ink present) from
    the 7-state QDA posterior, uniform state priors (alphabet is uniform by
    construction)."""
    ll = np.empty((X.shape[0], len(model.mu)))
    for s, (mu, ic, ld) in enumerate(zip(model.mu, model.icov, model.logdet)):
        d = X - mu
        ll[:, s] = -0.5 * (np.einsum("ij,jk,ik->i", d, ic, d) + ld)
    ll -= ll.max(axis=1, keepdims=True)
    post = np.exp(ll)
    post /= post.sum(axis=1, keepdims=True)
    out = np.empty((len(LEVELS), X.shape[0]))
    for i, p in enumerate(LEVELS):
        p1 = np.clip(post[:, MEMBER[p].astype(bool)].sum(axis=1),
                     POST_CLIP, 1 - POST_CLIP)
        out[i] = np.log(p1 / (1 - p1))
    return out


def checkerboard(shape: tuple[int, int]) -> np.ndarray:
    iy, ix = np.mgrid[0:shape[0], 0:shape[1]]
    return ((iy + ix) % 2 == 0).ravel()


def calibrate_splithalf(llr: np.ndarray, g: np.ndarray,
                        half: np.ndarray) -> np.ndarray:
    """Split-half PAVA recal (003.0a / decode_b1_tile construction): each
    half is calibrated by the map fit on the OTHER half. Returns the
    stitched calibrated LLR field (fold-honest per cell)."""
    err = (llr > 0) != g.astype(bool)
    out = np.empty_like(llr)
    for train in (half, ~half):
        c, p = k4.fit_monotone_map(np.abs(llr[train]), err[train])
        out[~train] = k4.apply_map(llr[~train], c, p)
    return out


def ldpc_overlay(cal_llr_tiles: list[np.ndarray], g_tiles: list[np.ndarray],
                 rungs: list[str]) -> dict:
    """Overlay measured calibrated LLR-toward-truth on real ladder codewords.
    All-zeros codeword (valid for any linear code; symmetric-channel
    overlay): channel LLR presented to decode = -e where
    e = cal_llr * (2*gt - 1) is the measured LLR toward the true bit.
    Blocks = consecutive 4096 cells in tile raster order (tile remainder
    dropped). Success = syndrome_ok AND all-zeros; syndrome-valid nonzero
    counted as wrong_decode."""
    res = {r: {"ok": 0, "fail": 0, "wrong": 0} for r in rungs}
    for cal, g in zip(cal_llr_tiles, g_tiles):
        e = cal * (2.0 * g.astype(np.float64) - 1.0)
        n_blk = e.size // ldpc.LDPC_LADDER[rungs[0]].n_bits
        for b in range(n_blk):
            L = -e[b * 4096:(b + 1) * 4096]
            for r in rungs:
                bits, syn, _ = ldpc.decode(L, ldpc.LDPC_LADDER[r])
                if syn and not bits.any():
                    res[r]["ok"] += 1
                elif syn:
                    res[r]["wrong"] += 1
                else:
                    res[r]["fail"] += 1
    for r in rungs:
        n = sum(res[r].values())
        res[r]["yield"] = res[r]["ok"] / max(n, 1)
        res[r]["n_blocks"] = n
    return res


def halve_errors(llr: np.ndarray, g: np.ndarray,
                 rng: np.random.Generator) -> np.ndarray:
    """ESTIMATE construction: un-flip a seeded random half of the measured
    error cells (sign -> toward truth, magnitude kept; magnitudes are then
    re-calibrated by the caller). Models the Canon 8px/dot ~2x BER
    improvement (014.2 measured 7.9->2.6% class of gain for c2-K)."""
    err_idx = np.flatnonzero((llr > 0) != g.astype(bool))
    fix = rng.choice(err_idx, size=err_idx.size // 2, replace=False)
    out = llr.copy()
    out[fix] = np.abs(out[fix]) * (2.0 * g[fix].astype(np.float64) - 1.0)
    return out


def analyze_scan(scan_path: str, do_ldpc: bool = True) -> dict:
    t0 = time.time()
    manifest = cc.load_manifest(ae.MANIFEST_PATH)
    scan = cc.load_scan(scan_path)
    reg = cc.register(scan, manifest)
    wm = cc.white_model(scan)
    print(f"[{Path(scan_path).name}] registered "
          f"(sha {scan.get('sha256', '?')[:12]})", flush=True)

    tiles = ae.tiles_of(manifest, "A3")
    feats, shapes, names = [], [], []
    for t in tiles:
        X, y = ae.tile_features(scan, wm, t["name"], "CMY")
        e0 = cc.entry(scan["manifest"], f"{t['name']}_C")
        st2d = cc.load_gt_named(e0["params"]["states_gt"], ae.BUILD)
        assert st2d.size == y.size
        feats.append((X, y))
        shapes.append(st2d.shape)
        names.append(t["name"])
        print(f"  features {t['name']}: {X.shape}", flush=True)

    # cross-tile QDA (legal footing): held-out tile scored by the other 15
    llr_tiles = {p: [] for p in LEVELS}   # raw posterior bit LLRs, per tile
    g_tiles = {p: [] for p in LEVELS}
    state_conf = np.zeros((7, 7), np.int64)
    for hold in range(len(feats)):
        Xtr = np.concatenate([X for i, (X, _) in enumerate(feats) if i != hold])
        ytr = np.concatenate([y for i, (_, y) in enumerate(feats) if i != hold])
        Xte, yte = feats[hold]
        model = ae.GaussianQDA().fit(Xtr, ytr, 7)
        bit_llrs = qda_posterior_llrs(model, Xte)
        pred = model.predict(Xte)
        for a, b in zip(yte, pred):
            state_conf[a, b] += 1
        for i, p in enumerate(LEVELS):
            llr_tiles[p].append(bit_llrs[i])
            g_tiles[p].append(MEMBER[p][yte])

    out: dict = {"scan": Path(scan_path).name, "scan_sha256": scan.get("sha256"),
                 "registration_scale": {"x_px_per_dot": float(scan["affine"][0]),
                                        "y_px_per_dot": float(scan["affine"][4])},
                 "n_tiles": len(feats),
                 "cells_per_tile": int(feats[0][1].size),
                 "state_confusion_7st": state_conf.tolist(),
                 "levels": {}}

    half_tiles = [checkerboard(s) for s in shapes]
    rng = np.random.default_rng(
        np.frombuffer(b"probe17/canon-halve" + Path(scan_path).name.encode(),
                      np.uint8).astype(np.uint64).sum())

    for p in LEVELS:
        llr_all = np.concatenate(llr_tiles[p])
        g_all = np.concatenate(g_tiles[p])
        half_all = np.concatenate(half_tiles)
        err = (llr_all > 0) != g_all.astype(bool)
        per_tile_ber = [float((((l > 0) != g.astype(bool))).mean())
                        for l, g in zip(llr_tiles[p], g_tiles[p])]

        cal_all = calibrate_splithalf(llr_all, g_all, half_all)
        rec = {
            "ber": float(err.mean()),
            "ber_per_tile_min": float(min(per_tile_ber)),
            "ber_per_tile_max": float(max(per_tile_ber)),
            "per_tile_ber": {n: b for n, b in zip(names, per_tile_ber)},
            "miss": float(err[g_all == 1].mean()),
            "fa": float(err[g_all == 0].mean()),
            "prior_p1": float(g_all.mean()),
            "mi_raw_bits": float(k4.mi_bits(llr_all, g_all)),
            "mi_cal_splithalf_bits": float(k4.mi_bits(cal_all, g_all)),
        }
        if do_ldpc:
            # split calibrated field back into tiles for raster blocking
            cal_tiles, off = [], 0
            for g in g_tiles[p]:
                cal_tiles.append(cal_all[off:off + g.size])
                off += g.size
            rec["ldpc_measured"] = ldpc_overlay(cal_tiles, g_tiles[p], RUNGS)
            # Canon-halved ESTIMATE
            llr_h = halve_errors(llr_all, g_all, rng)
            cal_h = calibrate_splithalf(llr_h, g_all, half_all)
            rec["ber_halved_ESTIMATE"] = float(
                (((llr_h > 0) != g_all.astype(bool))).mean())
            cal_h_tiles, off = [], 0
            for g in g_tiles[p]:
                cal_h_tiles.append(cal_h[off:off + g.size])
                off += g.size
            rec["ldpc_halved_ESTIMATE"] = ldpc_overlay(
                cal_h_tiles, g_tiles[p], RUNGS)
        out["levels"][p] = rec
        print(f"  level {p}: BER {rec['ber']:.4f} "
              f"(tiles {rec['ber_per_tile_min']:.4f}-{rec['ber_per_tile_max']:.4f}) "
              f"miss {rec['miss']:.4f} fa {rec['fa']:.4f} "
              f"MI raw {rec['mi_raw_bits']:.3f} cal {rec['mi_cal_splithalf_bits']:.3f}",
              flush=True)
        if do_ldpc:
            for tag in ("ldpc_measured", "ldpc_halved_ESTIMATE"):
                y = {r: f"{rec[tag][r]['yield']:.3f}" for r in RUNGS}
                w = sum(rec[tag][r]["wrong"] for r in RUNGS)
                print(f"    {tag}: {y} wrong={w}", flush=True)
    out["runtime_s"] = round(time.time() - t0, 1)
    return out


def net_density(rung_by_level: dict[str, str], dust_frac: float,
                pilot_frac: float = 0.0278, edge_frac: float = 0.026) -> float:
    """Net certified b/mm2 for the coded 8-state c3 page: 3 level bits/cell,
    per-level ladder rate x CRC tax, minus pilots + training dust + edge
    tiles. ARITHMETIC on measured rungs, labeled by the caller."""
    b_cell = 0.0
    for p, r in rung_by_level.items():
        spec = ldpc.LDPC_LADDER[r]
        b_cell += spec.rate * (1.0 - 32.0 / spec.k_bits)
    return CELLS_MM2_C3 * (1 - pilot_frac) * (1 - dust_frac) * \
        (1 - edge_frac) * b_cell


def main() -> None:
    scans = sys.argv[1:]
    if not scans:
        sys.exit(__doc__)
    report = {"probe": "P5-level-rates", "date": "2026-07-10",
              "footing": "e004 A3 7-state c3, cross-tile QDA, genie warp, "
                         "1200dpi home flatbed (2 px/dot)",
              "scans": [analyze_scan(s) for s in scans]}
    out = REPO / "experiments/017-color-channel/build/probe17_level_rates_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print(f"\nwrote {out}", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""P1-stagea-luma-margin: measured Stage-A word-site luma margin per candidate
dark rendering, on real toner.

Word sites in the color-channel design are luma-binary: bit=0 -> W (paper),
bit=1 -> a dark ink state. Candidates: CMY triple stack (calpage state8 only),
keystream-drawn 2-ink {CM,CY,MY}, any-ink mixture. This probe measures, on
real color scans with GT from the sha-gated generators:

  * oracle-threshold balanced BER (ceiling; monotone-transform invariant),
  * acquire.cell_bits_blind bits with the pinned-0.5/0.5 2-GMM fit over ALL
    cells of the tile/band (what Stage A actually runs on a 7/8-state page —
    the 50% ink assumption is violated; this measures the cost),
  * same GMM fit on a balanced W+dark site population (isolates fit-population
    cost from Gaussian-model cost),
  * exact-binomial (100,23) t=13 word-failure for every BER.

Data sources (all real scans, GT via the experiment gen modules):
  e004    A3 7-state c3 tiles, home M281 print (finalists-1-col.png) and
          AltaLink print (xerox-e004-finalists-hp-scan.png); genie warp via
          decode_rect_by_squares in the GREY channel against the C|M|Y union.
  calpage state8 8-state c3 field incl. the CMY triple (test-scan-calpage-
          color.png home; xerox-cal-hp-scan.png AltaLink print).
  e006c   16 state-field bands, STARVED-Y day (006col-scan-{2,3}-col.png),
          strip-tracked grey means (the loop-legal geometry).

Usage (from anywhere; env python):
  probe17_stagea_luma.py e004 <scan-path> <out-tag>
  probe17_stagea_luma.py calpage <scan-path> <out-tag>
  probe17_stagea_luma.py e006c <s2col|s3col> <out-tag>

Writes scratch/probe17_out/<out-tag>.json and prints a table.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import binom

_REPO = Path("<repo>")
for rel in ("experiments/004-finalists-checkerboard",
            "experiments/002-calibration-page",
            "experiments/003-modulation-probes",
            "experiments/001-engine-characterization",
            "experiments/006-loop-pages",
            "src"):
    p = str(_REPO / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

import cal_core as cc                      # noqa: E402
import scanlab                             # noqa: E402
import analyze_e004 as ae4                 # noqa: E402
import strip_tracker as st                 # noqa: E402
from paperholo.acquire import cell_bits_blind  # noqa: E402

OUT = _REPO / "scratch" / "probe17_out"
OUT.mkdir(exist_ok=True)

STATES7 = ("W", "C", "M", "Y", "CM", "CY", "MY")
# state8: bit0=C bit1=M bit2=Y (manifest semantics, gen_calpage.state_field)
STATE8_NAMES = ("W", "C", "M", "CM", "Y", "CY", "MY", "CMY")

# candidate dark sets (name -> member state names); singles are diagnostics
CANDIDATES = [
    ("triple_CMY", ("CMY",)),          # only exists in state8
    ("2ink_mix", ("CM", "CY", "MY")),
    ("anyink_mix", ("C", "M", "Y", "CM", "CY", "MY")),
    ("CM", ("CM",)), ("CY", ("CY",)), ("MY", ("MY",)),
    ("C", ("C",)), ("M", ("M",)), ("Y", ("Y",)),
]

T_WORD = 13   # (100,23) BCH window code corrects t=13
N_WORD = 100


def word_fail(p: float) -> float:
    """Exact binomial P[more than t errors in a 100-bit word]."""
    return float(binom.sf(T_WORD, N_WORD, min(max(p, 0.0), 1.0)))


def _balanced_pop(m: np.ndarray, names: np.ndarray, members: tuple[str, ...],
                  rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray] | None:
    """Balanced site population: all W cells + equal-count draws from each
    member dark state (total dark == n_white, keystream-equivalent 50/50)."""
    mw = m[names == "W"]
    per = [m[names == s] for s in members]
    if mw.size < 200 or any(x.size < 200 for x in per):
        return None
    k = mw.size // len(members)
    dark = np.concatenate([rng.choice(x, size=min(k, x.size), replace=False)
                           for x in per])
    pop = np.concatenate([mw, dark])
    lab = np.concatenate([np.zeros(mw.size, np.uint8),
                          np.ones(dark.size, np.uint8)])
    return pop, lab


def measure_window(m: np.ndarray, names: np.ndarray,
                   candidates=CANDIDATES) -> dict:
    """All metrics for one window (tile/band). m = raw grey cell means
    (ink dark), names = per-cell state name strings."""
    m = np.asarray(m, np.float64).ravel()
    names = np.asarray(names).ravel()
    rng = np.random.default_rng(17)   # measurement-only subsampling

    # Stage-A realistic: pinned 2-GMM fit over ALL cells of the window
    bits_all, _ = cell_bits_blind(m)

    res: dict = {"n_cells": int(m.size)}
    idx_w = names == "W"
    fa_all = float(bits_all[idx_w].mean())   # W read as ink (bit error on 0s)

    thr_grid = np.quantile(m, np.linspace(0.001, 0.999, 512))

    for cname, members in candidates:
        if any((names == s).sum() < 200 for s in members):
            continue
        # equal member weights = keystream-uniform draw
        miss_all = float(np.mean([1.0 - bits_all[names == s].mean()
                                  for s in members]))
        rec = {"fa_gmm_all": fa_all, "miss_gmm_all": miss_all,
               "ber_gmm_all": (fa_all + miss_all) / 2,
               "worst_gmm_all": max(fa_all, miss_all)}

        # oracle threshold on raw luma (balanced objective, equal weights)
        mw = m[idx_w]
        fa_t = np.array([(mw < t).mean() for t in thr_grid])
        miss_t = np.mean([[(m[names == s] >= t).mean() for t in thr_grid]
                          for s in members], axis=0)
        ber_t = (fa_t + miss_t) / 2
        i = int(np.argmin(ber_t))
        rec.update(ber_oracle=float(ber_t[i]), fa_oracle=float(fa_t[i]),
                   miss_oracle=float(miss_t[i]),
                   worst_oracle=float(max(fa_t[i], miss_t[i])))

        # sites-only pinned GMM (balanced 50/50 population)
        bp = _balanced_pop(m, names, members, rng)
        if bp is not None:
            pop, lab = bp
            bits_s, _ = cell_bits_blind(pop)
            fa_s = float(bits_s[lab == 0].mean())
            miss_s = float(1.0 - bits_s[lab == 1].mean())
            rec.update(ber_gmm_sites=(fa_s + miss_s) / 2,
                       fa_gmm_sites=fa_s, miss_gmm_sites=miss_s)

        for k in ("ber_gmm_all", "worst_gmm_all", "ber_oracle",
                  "worst_oracle", "ber_gmm_sites"):
            if k in rec:
                rec["wf_" + k] = word_fail(rec[k])
        res[cname] = rec

    # null control: score any-ink against 7-row-rolled GT (must be ~chance)
    names2d = None  # names is flat; roll on flat array with a large stride
    rolled = np.roll(names, 7001)
    iw = rolled == "W"
    if iw.sum() > 200:
        fa_n = float(bits_all[iw].mean())
        anymem = [s for s in ("C", "M", "Y", "CM", "CY", "MY")
                  if (rolled == s).sum() > 200]
        miss_n = float(np.mean([1.0 - bits_all[rolled == s].mean()
                                for s in anymem]))
        res["null_rolled_ber"] = (fa_n + miss_n) / 2

    # per-state mean luma (the margin picture)
    res["state_mean_luma"] = {s: float(m[names == s].mean())
                              for s in np.unique(names)}
    return res


# ---------------------------------------------------------------------------
# dataset drivers
# ---------------------------------------------------------------------------

def run_e004(scan_path: str) -> dict:
    manifest = cc.load_manifest(ae4.MANIFEST_PATH)
    scan = cc.load_scan(scan_path)
    cc.register(scan, manifest)
    windows = {}
    for t in ae4.tiles_of(manifest, "A3"):
        name = t["name"]
        e = cc.entry(manifest, f"{name}_C")
        states = cc.load_gt_named(e["params"]["states_gt"],
                                  ae4.BUILD).astype(np.int64)
        gts = [cc.load_gt(cc.entry(manifest, f"{name}_{p}")) for p in "CMY"]
        gt_union = (gts[0] | gts[1] | gts[2]).astype(np.uint8)
        out = ae4.decode_rect_by_squares(scan, e, gt_union, 3, "grey",
                                         soft=False, diagnostics=False)
        m = np.asarray(out["means"], np.float64)
        assert m.shape == states.shape, (name, m.shape, states.shape)
        names = np.array(STATES7, dtype=object)[states.ravel()]
        windows[name] = measure_window(m.ravel(), names)
        print(f"{name}: n={windows[name]['n_cells']} "
              f"anyink gmm-all {windows[name]['anyink_mix']['ber_gmm_all']:.4f} "
              f"oracle {windows[name]['anyink_mix']['ber_oracle']:.4f}",
              flush=True)
    return {"windows": windows}


def run_calpage(scan_path: str) -> dict:
    manifest = cc.load_manifest(
        _REPO / "experiments/002-calibration-page/build/calpage_manifest.json")
    scan = cc.load_scan(scan_path)
    cc.register(scan, manifest)
    e = cc.entry(manifest, "state8_C")
    build = _REPO / "experiments/002-calibration-page/build"
    states = cc.load_gt_named(e["params"]["states_gt"], build).astype(np.int64)
    gts = [cc.load_gt(cc.entry(manifest, f"state8_{p}")) for p in "CMY"]
    gt_union = (gts[0] | gts[1] | gts[2]).astype(np.uint8)
    out = scanlab.decode_cells(cc._channel_f32(scan, "grey"), scan["affine"],
                               e, gt_union, 3, soft=False, diagnostics=False)
    m = np.asarray(out["means"], np.float64)
    nc = min(m.shape[0], states.shape[0])
    m, states = m[:nc, :nc], states[:nc, :nc]
    names = np.array(STATE8_NAMES, dtype=object)[states.ravel()]
    win = measure_window(m.ravel(), names)
    print(f"state8: n={win['n_cells']} "
          f"triple gmm-all {win['triple_CMY']['ber_gmm_all']:.4f} "
          f"oracle {win['triple_CMY']['ber_oracle']:.4f}", flush=True)
    return {"windows": {"state8": win}}


def run_e006c(tag: str) -> dict:
    import analyze_e006c as a6c
    manifest = cc.load_manifest(a6c.BUILD / "e006c_manifest.json")
    band_meta = [b for b in manifest["bands"] if b["kind"] == "state_field"]
    strips = []
    for p in manifest["patches"]:
        if p["kind"] == "sync_strip":
            strips.append({**{k: p[k] for k in
                              ("x_dots", "y_dots", "w_dots", "h_dots")},
                           "gt": cc.load_gt(p)})
    scan = cc.load_scan(a6c.SCANS_DIR / a6c.SCANS[tag], compute_sha256=False)
    cc.register(scan, manifest, refine=False)
    coef = np.asarray(scan["affine"], np.float64)
    grey = cc._channel_f32(scan, "grey")
    tr = st.track_strips(grey, coef, strips)
    print(f"[{tag}] strip lock {float(np.isfinite(tr['dy']).mean()):.2f}",
          flush=True)
    windows = {}
    for b in band_meta:
        e = cc.entry(manifest, f"{b['name']}_C")
        m = st.strip_cell_means(grey, coef, e, 3, tr)
        y = cc.load_gt_named(b["params"]["states_gt"], a6c.BUILD)
        names = np.array(STATES7, dtype=object)[y.ravel().astype(np.int64)]
        windows[b["name"]] = measure_window(m.ravel(), names)
        w = windows[b["name"]]
        print(f"{b['name']}: n={w['n_cells']} "
              f"anyink gmm-all {w['anyink_mix']['ber_gmm_all']:.4f} "
              f"oracle {w['anyink_mix']['ber_oracle']:.4f}", flush=True)
    return {"windows": windows}


def summarize(payload: dict) -> None:
    wins = payload["windows"]
    cands = [c for c, _ in CANDIDATES
             if any(c in w for w in wins.values())]
    print(f"\n{'candidate':<12} {'oracle med/worst':<20} "
          f"{'gmm-all med/worst':<20} {'gmm-sites med':<14} "
          f"{'wf(gmm-all med/worst)':<24}")
    for c in cands:
        vals = [w[c] for w in wins.values() if c in w]
        om = np.median([v["ber_oracle"] for v in vals])
        ow = max(v["worst_oracle"] for v in vals)
        gm = np.median([v["ber_gmm_all"] for v in vals])
        gw = max(v["worst_gmm_all"] for v in vals)
        sm = (np.median([v["ber_gmm_sites"] for v in vals
                         if "ber_gmm_sites" in v])
              if any("ber_gmm_sites" in v for v in vals) else float("nan"))
        print(f"{c:<12} {om:.4f}/{ow:.4f}      {gm:.4f}/{gw:.4f}      "
              f"{sm:.4f}        {word_fail(gm):.2e}/{word_fail(gw):.2e}")
    nulls = [w.get("null_rolled_ber") for w in wins.values()
             if w.get("null_rolled_ber") is not None]
    if nulls:
        print(f"null (rolled GT) ber: {min(nulls):.3f}-{max(nulls):.3f}")


def main() -> None:
    mode, arg, tag = sys.argv[1], sys.argv[2], sys.argv[3]
    t0 = time.time()
    payload = {"mode": mode, "arg": arg,
               "run": {"e004": run_e004, "calpage": run_calpage,
                       "e006c": run_e006c}[mode](arg)}
    payload["runtime_s"] = round(time.time() - t0, 1)
    out = OUT / f"{tag}.json"
    out.write_text(json.dumps(payload, indent=1, default=float))
    summarize(payload["run"])
    print(f"\n-> {out}  ({payload['runtime_s']}s)")


if __name__ == "__main__":
    main()

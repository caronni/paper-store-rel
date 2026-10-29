#!/usr/bin/env python
"""cal_ber.py — experiment 002, modulation family: BER/MI matrix (CAL-1 page).

Decodes EVERY encode patch on the calibration page against its manifest ground
truth, with the scanlab v4 decoder (dense poly2 warp + step-preserving
y-profile + blind soft LLR stage) exactly as in experiment 001.4, so numbers
are directly comparable:

  - per plane K/C/M/Y  x  cell 1/2/3/4      (isolated-plane BER ladder, M1)
  - encode_K_ref                            (K cell=3 reference, 141x141 cells)
  - composite_c2_{C,M,Y}                    (3-plane composite, cell=2)
  - composite_c3_{C,M,Y}                    (3-plane composite, cell=3 — the
                                             real archive channel, M6)
  - Y_encode_c3                             (large Y cell=3 stress patch)

Method / policy
  - Decode primitives are used exclusively through cal_core (frozen contract):
    cc.decode_patch wraps scanlab.decode_cells v4 — genie-synced with the GT
    (registration templates + scoring ONLY; all decision statistics blind).
    scanlab functions are reached via cal_core's re-exports; nothing here
    hand-rolls resampling.
  - Channel policy: K patches are curated from the GREY scan (K rule) and
    cross-checked on the color scan's grey channel; C/M/Y and both composites
    are measured on the COLOR scan channels (C->r, M->g, Y->b via
    cc.reg_channel_for). Y is near-invisible in grey (contract §2).
  - NULL CONTROL (run-001.2 discipline): every decode carries cc.decode_patch's
    ber_null (same decoded bits vs 8-cell-shifted GT); required 0.50 +- 0.02.
    The naive fallback path (used only if v4 crashes, e.g. zero warp locks on a
    dead cell=1 patch) uses cc.ber_with_null the same way.
  - Confident BER: from the blind per-cell |LLR|, dropping the u most-uncertain
    cells: u in {5%, 10%} for the c3-class (cell_dots >= 3), {15%, 25%} for the
    c2-class (cell_dots <= 2). All four fractions live in the raw record.
  - No randomness anywhere in this module (CLAUDE.md determinism rule is
    satisfied vacuously; were any needed it would flow from
    paperholo.modulation.rng).

Report shape (merges into cal_core.report_init skeleton via cc.report_merge):
  modulation.{K,C,M,Y}.{c1..c4}            each {ber, ber_llr, mi_bits, conf,
                                                 null_ber, ...}
  modulation.K.c3_ref, modulation.Y.c3_large
  modulation.composite.{C,M,Y}             (the cell=3 composite, per brief)
  modulation.composite_c2.{C,M,Y}          (the cell=2 composite)
  families.modulation.ber_matrix.{method,patches,comparisons}

Smoke run (real scans, ~6-10 min):
  env/bin/python experiments/002-calibration-page/cal_ber.py \
      <evidence>/scans/test-scan-calpage-bw.png \
      <evidence>/scans/test-scan-calpage-color.png
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import cal_core as cc  # noqa: E402  (frozen analyzer core — do not edit)

PLANES: tuple[str, ...] = ("K", "C", "M", "Y")
CELLS: tuple[int, ...] = (1, 2, 3, 4)

# Confident-BER uncertain-erasure fractions (share of cells dropped, by |LLR|).
CONF_FRACS_ALL: tuple[float, ...] = (0.05, 0.10, 0.15, 0.25)
REF_001_4_K_C3_BER: tuple[float, float] = (0.020, 0.022)  # 001.4, v4 decoder


def conf_fracs_for(cell_dots: int) -> tuple[float, float]:
    """c3-class (cell>=3): 5/10 % uncertain; c2-class (cell<=2): 15/25 %."""
    return (0.05, 0.10) if cell_dots >= 3 else (0.15, 0.25)


def _conf_key(u: float) -> str:
    return f"u{int(round(u * 100)):02d}"


def _confident_ber(llr: np.ndarray, gt_cells_arr: np.ndarray,
                   fracs: tuple[float, ...]) -> dict:
    """BER over the (1-u) most-confident cells, per uncertain fraction u.

    Threshold = u-quantile of |LLR| (blind); error scored against GT.
    """
    gtb = gt_cells_arr.astype(bool)
    err = (llr > 0) != gtb
    a = np.abs(llr)
    out: dict[str, dict] = {}
    for u in fracs:
        t = float(np.quantile(a, u))
        sel = a >= t
        out[_conf_key(u)] = {
            "uncertain_frac": float(u),
            "kept_frac": float(sel.mean()),
            "llr_thresh": t,
            "ber_conf": float(err[sel].mean()) if sel.any() else None,
        }
    return out


def _naive_fallback(scan: dict, e: dict) -> dict:
    """Last-resort decode when v4 finds no warp lock (dead-channel patches).

    patch_view (GT-template local lock if it takes, else global affine) ->
    cell means -> local-median threshold -> BER + null control. No soft stage.
    Numbers from this path are upper bounds; a dead patch reads ~0.5 anyway.
    """
    cell = int(e["params"]["cell_dots"])
    v = cc.patch_view(scan, e)
    m = cc.cell_means(v, cell_dots=cell)
    g = cc.gt_cells(e)
    n = min(m.shape[0], g.shape[0], m.shape[1], g.shape[1])
    m, g = m[:n, :n], g[:n, :n]
    bits = (m < median_filter(m, size=min(31, 2 * (n // 2) - 1), mode="nearest"))
    bn = cc.ber_with_null(bits.astype(np.uint8), g)
    return {
        "method": "naive_fallback",
        "channel": v.reg_channel,
        "local_locked": bool(v.local_locked),
        "local_quality": v.local_quality,
        "ber": bn["ber"], "n_cells": bn["n_cells"],
        "null_ber": bn["ber_null"], "null_ok": bn["null_ok"],
        "ber_llr": None, "mi_bits": None, "conf": None,
    }


def decode_encode_patch(scan: dict, name: str, *, scan_tag: str,
                        overlay_hook=None) -> dict:
    """Full v4 decode + null control + confident BER for one encode patch.

    overlay_hook: optional callable(scan, name, decode_out) used by the
    orchestrator (analyze_calpage) to save per-patch error overlays while the
    decode arrays (err_map etc.) are still in memory. Advisory only: a hook
    failure is recorded in the record, never propagated into the measurement.
    """
    e = cc.entry(scan["manifest"], name)
    cell_dots = int(e["params"]["cell_dots"])
    rec: dict = {"patch": name, "scan": scan_tag, "cell_dots": cell_dots,
                 "plane": e["planes"][0], "w_dots": e["w_dots"]}
    t0 = time.time()
    try:
        out = cc.decode_patch(scan, name)
    except Exception as exc:  # dead patch: v4 needs >=1 warp lock
        rec.update(_naive_fallback(scan, e))
        rec["v4_error"] = f"{type(exc).__name__}: {exc}"
        rec["elapsed_s"] = round(time.time() - t0, 1)
        return rec
    soft = out.get("soft") or {}
    conf_all = _confident_ber(soft["llr"], out["gt_cells"], CONF_FRACS_ALL)
    fr = conf_fracs_for(cell_dots)
    rec.update({
        "method": "decode_cells_v4",
        "channel": out["channel"],
        "ber": out["ber"],
        "n_cells": out["cells"],
        "errors": out["errors"],
        "clustered": out["clustered"],
        "ber_llr": soft.get("ber_llr"),
        "ber_llr_ctx": soft.get("ber_llr_ctx"),
        "mi_bits": soft.get("mi_bits"),
        "mi_bits_ctx": soft.get("mi_bits_ctx"),
        "conf": {_conf_key(u): conf_all[_conf_key(u)] for u in fr},
        "conf_all": conf_all,
        "null_ber": out["ber_null"],
        "null_ok": out["null_ok"],
        "warp_windows_used": out["warp_windows_used"],
        "warp_windows_total": out["warp_windows_total"],
        "poly_resid_rms_dots": out["poly_resid_rms_dots"],
        "gmm": soft.get("gmm"),
        "transport_steps": [list(s) for s in out.get("steps", [])],
        "elapsed_s": round(time.time() - t0, 1),
    })
    if overlay_hook is not None:
        try:
            overlay_hook(scan, name, out)
        except Exception as exc:  # overlays are advisory, measurements are not
            rec["overlay_error"] = f"{type(exc).__name__}: {exc}"
            print(f"  [overlay] {name}: {rec['overlay_error']}", flush=True)
    return rec


def _curated(rec: dict) -> dict:
    """The report-schema view: {ber, ber_llr, mi_bits, conf, null_ber, ...}."""
    return {k: rec.get(k) for k in
            ("ber", "ber_llr", "mi_bits", "conf", "null_ber", "null_ok",
             "n_cells", "channel", "scan", "method")}


# ---------------------------------------------------------------------------
# family entry point
# ---------------------------------------------------------------------------

def run(scan_bw: dict | None, scan_color: dict,
        core_ctx: dict | None = None) -> dict:
    """Modulation-family BER/MI matrix. Returns a cc.report_merge payload.

    scan_bw/scan_color: cc.load_scan dicts (registered here if not already).
    core_ctx: optional shared context; honors 'overlay_hook' (callable
    (scan, name, decode_out) -> None, advisory per-patch overlay saver).
    """
    ctx = core_ctx or {}
    overlay_hook = ctx.get("overlay_hook")  # optional per-patch overlay saver
    for s in (scan_bw, scan_color):
        # load_scan pre-seeds 'registration' with None, so test the VALUE
        # (the original `"registration" not in s` check never fired).
        if s is not None and s.get("registration") is None:
            cc.register(s)

    raw: dict[str, dict] = {}

    def dec(scan: dict, name: str, tag: str) -> dict:
        rec = decode_encode_patch(scan, name, scan_tag=tag,
                                  overlay_hook=overlay_hook)
        raw[f"{tag}:{name}"] = rec
        b = rec.get("ber")
        bl = rec.get("ber_llr")
        mi = rec.get("mi_bits")
        nb = rec.get("null_ber")
        print(f"  {tag:5s} {name:16s} ch={rec.get('channel'):4s} "
              f"ber={b:.4f}" + (f" llr={bl:.4f}" if bl is not None else " llr=  -  ")
              + (f" mi={mi:+.3f}" if mi is not None else " mi=  -  ")
              + f" null={nb:.3f}{'' if rec.get('null_ok') else ' NULL-FAIL'}"
              + f" [{rec['method']}]", flush=True)
        return rec

    # color scan, grouped by scanner channel so the f32 cache (~560 MB each)
    # can be dropped between groups (contract §9.8 memory note).
    groups: list[tuple[str, list[str]]] = [
        ("r", [f"C/encode_c{n}" for n in CELLS]
              + ["composite_c2_C", "composite_c3_C"]),
        ("g", [f"M/encode_c{n}" for n in CELLS]
              + ["composite_c2_M", "composite_c3_M"]),
        ("b", [f"Y/encode_c{n}" for n in CELLS]
              + ["Y_encode_c3", "composite_c2_Y", "composite_c3_Y"]),
        ("grey", [f"K/encode_c{n}" for n in CELLS] + ["encode_K_ref"]),
    ]
    print("== color scan decodes ==", flush=True)
    for ch, names in groups:
        for nm in names:
            dec(scan_color, nm, "color")
        scan_color.get("_f32", {}).pop(ch, None)

    # grey scan: K patches (curated per the K rule — grey scan is primary for K)
    if scan_bw is not None:
        print("== grey (bw) scan decodes: K plane ==", flush=True)
        for nm in [f"K/encode_c{n}" for n in CELLS] + ["encode_K_ref"]:
            dec(scan_bw, nm, "bw")

    k_tag = "bw" if scan_bw is not None else "color"

    # ---- curated modulation matrix -------------------------------------
    modulation: dict = {}
    for p in PLANES:
        tag = k_tag if p == "K" else "color"
        modulation[p] = {f"c{n}": _curated(raw[f"{tag}:{p}/encode_c{n}"])
                         for n in CELLS}
    modulation["K"]["c3_ref"] = _curated(raw[f"{k_tag}:encode_K_ref"])
    modulation["Y"]["c3_large"] = _curated(raw["color:Y_encode_c3"])
    modulation["composite"] = {p: _curated(raw[f"color:composite_c3_{p}"])
                               for p in ("C", "M", "Y")}
    modulation["composite_c2"] = {p: _curated(raw[f"color:composite_c2_{p}"])
                                  for p in ("C", "M", "Y")}

    # ---- key comparisons -------------------------------------------------
    comp: dict = {}
    kc3 = raw[f"{k_tag}:K/encode_c3"]
    kref = raw[f"{k_tag}:encode_K_ref"]
    comp["k_c3_stationarity_vs_001_4"] = {
        "ref_001_4_ber": list(REF_001_4_K_C3_BER),
        "k_c3_ber": kc3["ber"], "k_c3_ber_llr": kc3["ber_llr"],
        "k_c3_ref_ber": kref["ber"], "k_c3_ref_ber_llr": kref["ber_llr"],
        "k_c3_ber_color_scan": raw["color:K/encode_c3"]["ber"],
        "k_scan_used": k_tag,
        "note": "same engine, different sheet/day than 001.4 — sheet-to-sheet "
                "stationarity check for the settled K cell=3 operating point",
    }
    comp["c3_by_plane_color_scan"] = {
        p: {"ber": raw[f"color:{p}/encode_c{3}"]["ber"],
            "ber_llr": raw[f"color:{p}/encode_c3"]["ber_llr"],
            "mi_bits": raw[f"color:{p}/encode_c3"]["mi_bits"]}
        for p in PLANES}
    for cn in ("c2", "c3"):
        d = {}
        for p in ("C", "M", "Y"):
            iso = raw[f"color:{p}/encode_{cn}"]
            co = raw[f"color:composite_{cn}_{p}"]
            d[p] = {"ber_isolated": iso["ber"], "ber_composite": co["ber"],
                    "ber_delta": co["ber"] - iso["ber"],
                    "mi_isolated": iso["mi_bits"], "mi_composite": co["mi_bits"],
                    "mi_delta": (None if None in (co["mi_bits"], iso["mi_bits"])
                                 else co["mi_bits"] - iso["mi_bits"])}
        comp[f"composite_minus_isolated_{cn}"] = d
    if scan_bw is not None:
        comp["k_grey_vs_color_scan"] = {
            f"c{n}": {"ber_bw": raw[f"bw:K/encode_c{n}"]["ber"],
                      "ber_color": raw[f"color:K/encode_c{n}"]["ber"]}
            for n in CELLS}

    null_fails = [k for k, r in raw.items() if not r.get("null_ok")]

    payload = {
        "modulation": modulation,
        "families": {"modulation": {"ber_matrix": {
            "method": {
                "decoder": "scanlab.decode_cells v4 via cal_core.decode_patch "
                           "(dense poly2 warp + step-preserving y-profile + "
                           "blind soft LLR; GT for registration templates and "
                           "scoring only) — 001.4-comparable",
                "channel_policy": "K curated from grey scan (K rule), "
                                  "cross-checked on color-scan grey; C/M/Y and "
                                  "composites on color scan r/g/b",
                "null_control": "decoded bits vs 8-cell-shifted GT, accept "
                                "0.50 +- 0.02 (001.2 discipline)",
                "conf_ber": "blind |LLR| quantile erasure; u=5/10% for "
                            "cell>=3, u=15/25% for cell<=2; all four "
                            "fractions in raw records",
            },
            "patches": raw,
            "comparisons": comp,
            "null_control_failures": null_fails,
        }}},
    }
    if null_fails:
        print(f"!! NULL CONTROL FAILURES (analyzer bug flag): {null_fails}",
              flush=True)
    return payload


# ---------------------------------------------------------------------------
# smoke block: end-to-end on the real scans
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    bw_path, color_path = sys.argv[1], sys.argv[2]

    t0 = time.time()
    print(f"loading + registering {color_path}", flush=True)
    scan_color = cc.load_scan(color_path)
    cc.register(scan_color)
    r = scan_color["registration"]
    print(f"  color: {r['n_landmarks_used']}/{r['n_landmarks_total']} landmarks,"
          f" rms {r['residual_rms_dots']:.2f} dots", flush=True)
    print(f"loading + registering {bw_path}", flush=True)
    scan_bw = cc.load_scan(bw_path)
    cc.register(scan_bw)
    r = scan_bw["registration"]
    print(f"  bw:    {r['n_landmarks_used']}/{r['n_landmarks_total']} landmarks,"
          f" rms {r['residual_rms_dots']:.2f} dots", flush=True)

    payload = run(scan_bw, scan_color)

    rep = cc.report_init(scan_color)
    cc.report_merge(rep, payload)
    out_path = cc.BUILD / "cal_ber_report.json"
    cc.save_report(rep, out_path)

    m = payload["modulation"]
    print("\n== BER matrix (hard / LLR-sign / MI bits per cell) ==")
    for p in PLANES:
        row = []
        for n in CELLS:
            e = m[p][f"c{n}"]
            row.append(f"c{n} {e['ber']:.3f}/" +
                       (f"{e['ber_llr']:.3f}" if e['ber_llr'] is not None else "  -  ") +
                       "/" + (f"{e['mi_bits']:+.2f}" if e['mi_bits'] is not None else "  -  "))
        print(f"  {p} ({m[p]['c1']['scan']}): " + "  ".join(row))
    e = m["K"]["c3_ref"]
    print(f"  K c3_ref: {e['ber']:.4f}/{e['ber_llr']:.4f}/mi {e['mi_bits']:+.3f}")
    e = m["Y"]["c3_large"]
    print(f"  Y c3_large: {e['ber']:.4f}/{e['ber_llr']:.4f}/mi {e['mi_bits']:+.3f}")
    for cn, key in (("c2", "composite_c2"), ("c3", "composite")):
        print(f"  composite {cn}: " + "  ".join(
            f"{p} {m[key][p]['ber']:.3f}/mi {m[key][p]['mi_bits']:+.2f}"
            if m[key][p]['mi_bits'] is not None else f"{p} {m[key][p]['ber']:.3f}/-"
            for p in ("C", "M", "Y")))
    comp = payload["families"]["modulation"]["ber_matrix"]["comparisons"]
    s = comp["k_c3_stationarity_vs_001_4"]
    print(f"\n  K c3 stationarity: this sheet {s['k_c3_ber']:.4f} "
          f"(ref patch {s['k_c3_ref_ber']:.4f}) vs 001.4 "
          f"{s['ref_001_4_ber'][0]:.3f}-{s['ref_001_4_ber'][1]:.3f}")
    for cn in ("c2", "c3"):
        d = comp[f"composite_minus_isolated_{cn}"]
        print(f"  composite-isolated delta {cn}: " + "  ".join(
            f"{p} {d[p]['ber_delta']:+.4f}" for p in ("C", "M", "Y")))
    nf = payload["families"]["modulation"]["ber_matrix"]["null_control_failures"]
    print(f"  null-control failures: {nf if nf else 'none'}")
    print(f"\nreport: {out_path}  ({time.time() - t0:.0f} s total)")

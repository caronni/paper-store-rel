#!/usr/bin/env python
"""analyze_overlap2.py — experiment 002.2: overlap-fidelity 2 + screened-channel
cell sweep, on the ONE overlap2 sheet (build/overlap2.ps, jobid f8e2bf4d).

Two headlines, one scan (scans/test-scan-overlap2.png):

BLOCK B — S-variant verdict (S1 Separation masks + setoverprint, S2 + OPM
dance, S3 DeviceN CMY image), per the 002.1 decision rule with IDENTICAL
analysis parameters (functions imported from analyze_composite_probe, gates
unchanged):
  1. screening  — canary-A 2-D spectra with GT-spectrum controls; the control
     bar is the SAME-SHEET clean single-plane imagemask refs (A4 block).
  2. knockout   — per-plane v4 decode of the CM/CMY fields, miss rate at
     overlap vs clear sites (union of later-painted planes).
  3. solids     — CM-solid interior medians vs the 002.1 anchors (same
     scanner, same day; cross-sheet — stated).
  BER bar: the 002.1 P4 single-plane c3 references (cross-sheet: this sheet
  carries no c3 single-plane refs; deviation from the 002.1 same-scan rule is
  recorded in the report).

BLOCK A — alphabet sweep through the screened put_cmyk_bitmap path:
  - 7-state {W,C,M,Y,CM,CY,MY} fields at c3/c4/c6 + 8-state {7+K} at c4:
    per-cell 3-channel density features via decode-grade per-plane alignment
    (cal_color.aligned_cell_densities), QDA confusion (cal_color machinery,
    same deterministic interleaved folds), uniform MI, Blahut-Arimoto capacity
    + exhaustive best-uniform-subset search (port of the 002.0c analysis),
    multiclass shifted-GT null on every field.
  - binary 3-plane 50% composites c4/c6: per-plane v4 hard BER + hard-decision
    MI vs the SAME-SHEET A4 mask refs and vs 002.0's c3 composite numbers;
    PLUS an unmixed-density decode variant using the measured crosstalk matrix
    (calpage_report.json channel_params.crosstalk_matrix) — the 002.0/002.1
    'unmix TODO'. A rigid raw-channel decode on the same registration is
    reported alongside so the unmix delta is attributable to unmixing, not to
    the alignment method.
  - screening spectra vs cell size: screen-family disk excess relative to each
    field's own GT-spectrum control at c3/c4/c6 (does the screen tax shrink?).

Discipline (001.2): every field decode carries the 8-cell-shift null control;
every classifier carries the shifted-GT multiclass null; no per-variant or
per-cell-size parameter tuning anywhere.

Determinism: no randomness in this module (QDA folds are cal_color's
deterministic interleave).

Run (repo root, ~5-10 min):
  env/bin/python experiments/002-calibration-page/analyze_overlap2.py \
      scans/test-scan-overlap2.png
Outputs: build/overlap2_report.json, build/RESULTS-002.2-draft.md,
human summary on stdout.
"""
from __future__ import annotations

import itertools
import math
import sys
import time
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import analyze_composite_probe as acp  # noqa: E402  (002.1 discriminators — reused verbatim)
import cal_color as ccol  # noqa: E402  (QDA/MI machinery — reused verbatim)
import cal_core as cc  # noqa: E402     (frozen analyzer core)

REPO = _HERE.parent.parent
MANIFEST_PATH = cc.BUILD / "overlap2_manifest.json"
DEFAULT_SCAN = REPO / "scans" / "test-scan-overlap2.png"
EXPECTED_SCAN_SHA256 = ("19e58f247c31faf7e55a2a1aa303f2e8cafb22c6"
                        "4a150bfe2b66b146e588be62")
OUT_REPORT = cc.BUILD / "overlap2_report.json"
OUT_DRAFT = cc.BUILD / "RESULTS-002.2-draft.md"

S_VARIANTS: tuple[str, ...] = ("S1", "S2", "S3")
S_FIELD_PATCHES: tuple[str, ...] = ("field_cm_C", "field_cm_M",
                                    "field_cmy_C", "field_cmy_M", "field_cmy_Y")
PRIMARY_CHANNEL = ccol.PRIMARY_CHANNEL           # C->r, M->g, Y->b

# ---- cross-sheet anchors (same scanner, same day — cross-sheet caveat applies
# ---- everywhere they are used; provenance: build/composite_probe_report.json
# ---- and build/calpage_report.json / experiments/002-calibration-page.md) ---
ANCHORS_002_1: dict = {
    "scan": "scans/test-scan-composite-probe.png (sha c0187114...)",
    # P4 single-plane imagemask c3 refs, same-day scan (BER bar for Block B):
    "p4_ref_ber_c3": {"C": 0.044815, "M": 0.045461, "Y": 0.082735},
    # raw r-channel interior medians (greylevels 0-255):
    "solid_r_median": {"C100": 17.0, "M100": 218.6, "P0_CM": 49.5,
                       "knockout_CM_lo": 219.0, "knockout_CM_hi": 220.0},
    # interior densities (that sheet's white model):
    "solid_D": {"C100_D_r": 1.1626, "M100_D_r": 0.0533,
                "C100_D_g": 0.2646, "M100_D_g": 2.4001},
    # P0 (put_cmyk_bitmap, screened+overlap-preserving) field BER anchors:
    "p0_field_ber": {"field_cm_C": 0.0614, "field_cm_M": 0.0554,
                     "field_cmy_C": 0.0975, "field_cmy_M": 0.126,
                     "field_cmy_Y": 0.201},
}
ANCHORS_002_0: dict = {
    "scan": "scans/test-scan-calpage-color.png (sha 2bbb8704...)",
    "mi8_c3_uniform": 1.757, "cap8_c3": 1.893, "best7_c3": 1.890,
    "best7_set": ["W", "C", "M", "Y", "CM", "CY", "MY"],
    "composite_c3_ber": {"C": 0.088, "M": 0.118, "Y": 0.240},
    "clean_c3_ber": {"K": 0.0374, "C": 0.0357, "M": 0.0381, "Y": 0.0718},
    "clean_c3_mi": {"K": 0.85, "C": 0.78, "M": 0.88, "Y": 0.75},
}
# Block B BER gate: 002.1 rule (ref + 0.02), refs = 002.1 P4 (cross-sheet).
BER_GATE_ABS = acp.BER_GATE_ABS
# c3 stationarity call: position/sheet variance scale from 002.0 (same-page
# replicas differed by ~1 pp BER ~ 0.05-0.1 bit); threshold stated, not tuned.
STATIONARITY_TOL_BITS = 0.08


def _cells_per_mm2(cell_dots: int) -> float:
    return (cc.HW_DPI / (cell_dots * 25.4)) ** 2


def _h2(p: float) -> float:
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return float(-p * math.log2(p) - (1 - p) * math.log2(1 - p))


def _mi_bsc_bits(ber: float) -> float:
    """Hard-decision MI of a symmetric binary channel at this BER (used ONLY
    to convert the 002.0 composite c3 BER anchors; marked derived)."""
    return 1.0 - _h2(ber)


def _hard_mi_bits(gt_cells_arr: np.ndarray, pred_bits: np.ndarray) -> float:
    conf = ccol._confusion(gt_cells_arr.ravel().astype(np.int64),
                           pred_bits.ravel().astype(np.int64), 2)
    return ccol._mi_bits_from_counts(conf)


def _free_f32(scan: dict) -> None:
    scan.pop("_f32", None)


# ---------------------------------------------------------------------------
# Blahut-Arimoto capacity + exhaustive uniform-subset search (002.0c port)
# ---------------------------------------------------------------------------

def _row_normalize(counts: np.ndarray) -> np.ndarray:
    W = counts.astype(np.float64)
    return W / np.maximum(W.sum(axis=1, keepdims=True), 1.0)


def _mi_bits_input(p_in: np.ndarray, W: np.ndarray) -> float:
    """I(X;Y) in bits for input dist p_in over channel W (rows P(y|x))."""
    joint = p_in[:, None] * W
    return ccol._mi_bits_from_counts(joint * 1e9)  # scale-invariant


def blahut_arimoto(W: np.ndarray, max_iter: int = 5000,
                   tol_bits: float = 1e-9) -> dict:
    """Channel capacity of the confusion-estimated DMC (rows P(y|x))."""
    nx = W.shape[0]
    p = np.full(nx, 1.0 / nx)
    lo = hi = 0.0
    it = 0
    for it in range(max_iter):
        q = p @ W
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where((W > 0) & (q > 0), W / np.maximum(q, 1e-300), 1.0)
            d = (W * np.log(ratio)).sum(axis=1)          # nats
        lo = float((p * d).sum() / math.log(2))
        hi = float(d.max() / math.log(2))
        if hi - lo < tol_bits:
            break
        p = p * np.exp(d)
        p = p / p.sum()
    return {"capacity_bits": lo, "capacity_upper_bits": hi,
            "input_dist": [float(v) for v in p], "iterations": it + 1}


def best_uniform_subsets(counts: np.ndarray, state_names: list[str]) -> dict:
    """Exhaustive uniform-input subset search over the confusion channel
    (002.0c method): best subset per size, full output alphabet kept."""
    W = _row_normalize(counts)
    n = W.shape[0]
    best: dict[str, dict] = {}
    for k in range(2, n + 1):
        top_mi, top_set = -1.0, None
        for sub in itertools.combinations(range(n), k):
            p = np.zeros(n)
            p[list(sub)] = 1.0 / k
            mi = _mi_bits_input(p, W)
            if mi > top_mi:
                top_mi, top_set = mi, sub
        best[str(k)] = {"states": [state_names[i] for i in top_set],
                        "mi_bits": top_mi}
    return best


# ---------------------------------------------------------------------------
# cell-size-aware screening spectra (acp machinery, parametrized lattice)
# ---------------------------------------------------------------------------

def _offgt_stats_cell(exc_print: np.ndarray, exc_gt: np.ndarray | None,
                      fx: np.ndarray, fy: np.ndarray, cell_dots: int) -> dict:
    """acp._offgt_stats with the cell-lattice exclusion at this patch's own
    cell pitch (Block A fields are c3/c4/c6; acp hardcodes c3)."""
    FX, FY, r = acp._freq_grids(fx, fy)
    base = (r > 0.04) & (r < 0.9)
    lat = acp._lattice_bins(FX, FY, cell_dots)
    art = acp._artifact_bins(FX, FY)
    mask = base & ~lat & ~art
    ctrl = None
    if exc_gt is not None:
        from scipy import ndimage
        gt_peaks = ndimage.maximum_filter(exc_gt, size=5) > 6.0
        mask = mask & ~gt_peaks
        ctrl = float(exc_gt[mask].max())
    stat = float(exc_print[mask].max())
    i, j = np.unravel_index(int(np.argmax(np.where(mask, exc_print, -np.inf))),
                            exc_print.shape)
    f_pk = (float(FX[i, j]), float(FY[i, j]))
    return {"max_offgt_peak_db": stat, "gt_control_db": ctrl,
            "peak_freq_cyc_per_dot": list(f_pk),
            "peak_lpi": float(math.hypot(*f_pk) * cc.HW_DPI),
            "peak_angle_deg": float(math.degrees(math.atan2(f_pk[1], f_pk[0]))),
            "cell_lattice_peak_db": float(exc_print[base & lat].max()),
            "scanchain_artifact_peak_db": float(exc_print[base & art].max()),
            "n_offgt_bins": int(mask.sum())}


def screening_field_cell(scan: dict, name: str, gt_exc_cache: dict) -> dict:
    """acp.screening_field, but the lattice exclusion uses the patch's own
    cell_dots and the GT cache is keyed by full name (contents are unique)."""
    v = cc.patch_view(scan, name)
    cell_dots = int(v.entry["params"]["cell_dots"])
    exc_p, fx, fy = acp._excess_db(v.crop())
    if name not in gt_exc_cache:
        gt = cc.load_gt(v.entry)
        gt_raster = np.kron((1.0 - gt).astype(np.float32) * 255.0,
                            np.ones((v.sub, v.sub), np.float32))
        gt_exc_cache[name] = acp._excess_db(gt_raster)[0]
    exc_g = gt_exc_cache[name]
    st = _offgt_stats_cell(exc_p, exc_g, fx, fy, cell_dots)
    fams = {fam: acp.disk_excess(exc_p, fx, fy, f)
            for fam, f in acp.SCREEN_FAMILIES.items()}
    floors = {fam: acp.disk_excess(exc_g, fx, fy, f)
              for fam, f in acp.SCREEN_FAMILIES.items()}
    return {"patch": name, "channel": v.reg_channel, "cell_dots": cell_dots,
            "locked": bool(v.local_locked), "q": v.local_quality,
            "family_excess_db": fams, "family_gt_floor_db": floors, **st}


# ---------------------------------------------------------------------------
# Block B — S-variant discriminators (002.1 rule, same gates)
# ---------------------------------------------------------------------------

def s_solids(scan: dict, wm: dict) -> dict:
    """CM-solid interior medians (raw greylevels + densities) per S variant vs
    the 002.1 anchors (cross-sheet: this sheet has no C100/M100 solids)."""
    a = ANCHORS_002_1
    r_c, r_m = a["solid_r_median"]["C100"], a["solid_r_median"]["M100"]
    out: dict = {"anchors": {k: a[k] for k in ("solid_r_median", "solid_D")},
                 "anchor_note": "002.1 sheet, same scanner+day (cross-sheet)"}
    for vid in S_VARIANTS:
        v = cc.patch_view(scan, f"{vid}/solid_cm_C")
        dens = cc.density(v, wm, channels=("r", "g", "b"))
        med_raw, med_d = {}, {}
        for ch in ("r", "g", "b"):
            crop = ccol._central_crop(v.channels[ch].astype(np.float64), v)
            med_raw[ch] = float(np.median(crop))
            med_d[ch] = float(np.median(ccol._central_crop(dens[ch], v)))
        # presence via 002.1 density arithmetic (anchor densities, cross-sheet)
        pres_c_d = (med_d["r"] - a["solid_D"]["M100_D_r"]) / a["solid_D"]["C100_D_r"]
        pres_m_d = (med_d["g"] - a["solid_D"]["C100_D_g"]) / a["solid_D"]["M100_D_g"]
        # presence on raw r-medians (eyeball-comparable): 1 = C100-dark, 0 = M-only
        pres_c_r = (r_m - med_raw["r"]) / max(r_m - r_c, 1e-6)
        if pres_c_d <= acp.PRESENCE_KNOCKOUT_MAX:
            verdict = "C_knocked_out"
        elif pres_c_d >= acp.PRESENCE_PRESERVED_MIN:
            verdict = "both_inks_present"
        else:
            verdict = "partial"
        out[vid] = {"median_raw_rgb": med_raw, "median_D_rgb": med_d,
                    "locked": bool(v.local_locked),
                    "presence_C_under_M_density": float(pres_c_d),
                    "presence_M_over_C_density": float(pres_m_d),
                    "presence_C_under_M_rmedian": float(pres_c_r),
                    "solid_verdict": verdict}
    return out


def block_b(scan: dict, manifest: dict, wm: dict) -> dict:
    # --- screening: S fields (c3, acp verbatim) vs A4 clean-ref control bar --
    print("Block B screening spectra ...", flush=True)
    cacheB: dict = {}
    cacheA: dict = {}
    screening: dict = {}
    for vid in S_VARIANTS:
        dets = [acp.screening_field(scan, f"{vid}/{pn}", cacheB)
                for pn in S_FIELD_PATCHES]
        screening[vid] = {"patches": dets,
                          "verdict": acp.variant_screening_verdict(dets)}
        print(f"  {vid}: screened_fc="
              f"{screening[vid]['verdict']['screened_fc']}", flush=True)
    a4_dets = [screening_field_cell(scan, f"A4/ref_{p}_c4", cacheA)
               for p in "CMY"]
    a4_verdict = acp.variant_screening_verdict(a4_dets)
    baseline_fc = set(a4_verdict["screened_fc"])
    print(f"  A4 baseline (c4 mask refs) screened_fc={sorted(baseline_fc)}",
          flush=True)
    for vid in S_VARIANTS:
        v_ = screening[vid]["verdict"]
        v_["beyond_A4_baseline"] = sorted(set(v_["screened_fc"]) - baseline_fc)
    qz = acp.screening_quiet_zone(scan)

    # --- knockout + BER: 15 v4 decodes, grouped by channel (memory) ---------
    print("Block B field decodes (v4 hard, null-controlled) ...", flush=True)
    fields: dict[str, dict] = {}
    groups = [("r", [f"{v}/{f}_C" for v in S_VARIANTS
                     for f in ("field_cm", "field_cmy")]),
              ("g", [f"{v}/{f}_M" for v in S_VARIANTS
                     for f in ("field_cm", "field_cmy")]),
              ("b", [f"{v}/field_cmy_Y" for v in S_VARIANTS])]
    for ch, names in groups:
        for nm in names:
            rec = acp.decode_field(scan, manifest, nm)
            fields[nm] = rec
            extra = ""
            if "split_under" in rec:
                s = rec["split_under"]
                extra = (f" miss@ovl={s['miss_overlap']['err']:.3f}"
                         f"/clr={s['miss_clear']['err']:.3f}"
                         f"{' KNOCKOUT' if rec.get('knockout_flag') else ''}")
            print(f"  {nm:18s} ch={rec['channel']} ber={rec['ber']:.4f} "
                  f"null={rec['null_ber']:.3f}"
                  f"{'' if rec['null_ok'] else ' NULL-FAIL'}{extra}", flush=True)
        scan.get("_f32", {}).pop(ch, None)

    # --- solids --------------------------------------------------------------
    print("Block B CM solids ...", flush=True)
    solids = s_solids(scan, wm)
    for vid in S_VARIANTS:
        s = solids[vid]
        print(f"  {vid} solid_cm: r/g/b median="
              f"{s['median_raw_rgb']['r']:.1f}/{s['median_raw_rgb']['g']:.1f}/"
              f"{s['median_raw_rgb']['b']:.1f}  presC(D)="
              f"{s['presence_C_under_M_density']:+.2f} -> {s['solid_verdict']}",
              flush=True)

    # --- verdicts (002.1 decision rule; BER bar = 002.1 P4 c3, cross-sheet) --
    ref_ber = ANCHORS_002_1["p4_ref_ber_c3"]
    null_failures = [nm for nm, r_ in fields.items() if not r_["null_ok"]]
    variants: dict[str, dict] = {}
    for vid in S_VARIANTS:
        v_fields = {nm: rec for nm, rec in fields.items()
                    if nm.startswith(vid + "/")}
        screen_free = not screening[vid]["verdict"]["beyond_A4_baseline"]
        ko_flags = {nm: rec.get("knockout_flag") for nm, rec in v_fields.items()
                    if "knockout_flag" in rec}
        knockout_free = (not any(ko_flags.values())
                         and solids[vid]["solid_verdict"] == "both_inks_present")
        ber_delta = {nm: rec["ber"] - ref_ber[rec["plane"]]
                     for nm, rec in v_fields.items()}
        ber_ok = all(d <= BER_GATE_ABS for d in ber_delta.values())
        variants[vid] = {
            "screen_free": screen_free,
            "screened_fc": screening[vid]["verdict"]["screened_fc"],
            "screened_beyond_A4": screening[vid]["verdict"]["beyond_A4_baseline"],
            "knockout_flags": ko_flags,
            "solid_verdict": solids[vid]["solid_verdict"],
            "knockout_free": knockout_free,
            "overlap_preserved": knockout_free,
            "ber_delta_vs_002_1_P4": ber_delta,
            "ber_within_gate": ber_ok,
            "qualifies": bool(screen_free and knockout_free and ber_ok),
        }
    adopted = None
    if not null_failures:
        for vid in S_VARIANTS:
            if variants[vid]["qualifies"]:
                adopted = vid
                break
    decision = {
        "rule": "adopt the first S-variant that is screen-free (no screened "
                "family|channel beyond the A4 clean-ref bar) AND knockout-free "
                f"AND per-plane BER within +{BER_GATE_ABS} of the single-plane "
                "c3 refs (002.1 rule; refs are the 002.1 P4 patches — "
                "CROSS-SHEET, same scanner+day, because this sheet has no c3 "
                "single-plane refs)",
        "adopted": adopted,
        "null_control_failures": null_failures,
        "A4_baseline_screened_fc": sorted(baseline_fc),
    }
    return {"screening": screening, "a4_baseline": {"patches": a4_dets,
                                                    "verdict": a4_verdict},
            "quiet_zone_control": qz, "fields": fields, "solids": solids,
            "variants": variants, "decision": decision}


# ---------------------------------------------------------------------------
# Block A — alphabet fields (QDA + BA), composites (+unmix), refs, screen tax
# ---------------------------------------------------------------------------

def _member_matrix(state_names: list[str], planes: str) -> np.ndarray:
    """(n_states, n_planes) 0/1: plane membership by state NAME spelling."""
    return np.array([[int(p in s) for p in planes] for s in state_names],
                    np.uint8)


def _check_state_gt(manifest: dict, field: str, planes_present: str,
                    state_names: list[str], states: np.ndarray) -> None:
    member = _member_matrix(state_names, planes_present)
    for i, p in enumerate(planes_present):
        gc = cc.gt_cells(cc.entry(manifest, f"{field}_{p}"))
        if gc is None or not np.array_equal(gc, member[states][:, :, i]):
            raise AssertionError(f"{field}_{p}: cell GT != state membership "
                                 "(manifest semantics violated)")


def measure_alphabet_field(scan: dict, wm: dict, field: str,
                           planes_present: str) -> dict:
    """QDA confusion + MI + BA capacity + best-subsets for one state field.
    Features: per-cell densities D_r/D_g/D_b, each aligned to its own plane's
    printed lattice (cal_color decode-grade alignment)."""
    e = cc.entry(scan["manifest"], f"{field}_C")
    state_names: list[str] = e["params"]["state_names"]
    n_states = len(state_names)
    cell_dots = int(e["params"]["cell_dots"])
    states = cc.load_gt_named(e["params"]["states_gt"]).astype(np.int64)
    _check_state_gt(scan["manifest"], field, planes_present, state_names, states)

    feats, feat_names, per_plane = [], [], {}
    for p in "CMY":
        D, summ = ccol.aligned_cell_densities(scan, f"{field}_{p}", wm)
        if D.shape != states.shape:
            raise RuntimeError(f"{field}_{p}: cell grid {D.shape} != states "
                               f"{states.shape}")
        feats.append(D.ravel())
        feat_names.append(f"D_{PRIMARY_CHANNEL[p]}({p}-aligned)")
        per_plane[p] = summ
    X3 = np.stack(feats, axis=1)
    y = states.ravel()

    res = ccol._gaussian_cv_classify(X3, y, n_states)
    null = ccol._classifier_null(res["pred"], states, n_states)
    ba = blahut_arimoto(_row_normalize(res["confusion"]))
    subsets = best_uniform_subsets(res["confusion"], state_names)

    # per-label (plane-presence) bit view — MLC framing
    member = _member_matrix(state_names, planes_present)
    bit_view = {}
    for i, p in enumerate(planes_present):
        true_bit = member[y][:, i]
        pred_bit = member[np.maximum(res["pred"], 0)][:, i]
        err = float((true_bit != pred_bit).mean())
        bit_view[p] = {"bit_err": err, "mi_bsc_bits": _mi_bsc_bits(err)}

    out = {
        "field": field, "n_states": n_states, "state_names": state_names,
        "cell_dots": cell_dots, "n_cells": int(y.size),
        "features": feat_names,
        "accuracy": res["accuracy"], "mi_bits_uniform": res["mi_bits"],
        "capacity_bits": ba["capacity_bits"],
        "capacity_input_dist": ba["input_dist"],
        "best_uniform_subsets": subsets,
        "confusion": res["confusion"].tolist(),
        "class_counts": res["class_counts"].tolist(),
        "class_mean_D": res["class_means"].tolist(),
        "label_bit_view": bit_view,
        "null": null,
        "per_plane_decode": per_plane,
    }
    if "K" in planes_present:  # 4-D variant with K-aligned grey density (raw)
        D_k, summ_k = ccol.aligned_cell_densities(scan, f"{field}_K", wm)
        per_plane["K"] = summ_k
        if D_k.shape == states.shape:
            X4 = np.column_stack([X3, D_k.ravel()])
            res4 = ccol._gaussian_cv_classify(X4, y, n_states)
            out["variant_4d"] = {
                "features": feat_names + ["D_grey(K-aligned)"],
                "accuracy": res4["accuracy"], "mi_bits": res4["mi_bits"],
                "null": ccol._classifier_null(res4["pred"], states, n_states)}
    return out


def decode_composite_plane(scan: dict, manifest: dict, field: str, plane: str
                           ) -> dict:
    """v4 hard decode of one composite plane + crosstalk splits by the union
    of the OTHER planes' ink (no knockout expected on the cmyk-image path —
    the split diagnoses crosstalk, esp. Y false positives over C/M)."""
    e = cc.entry(manifest, f"{field}_{plane}")
    cell_dots = int(e["params"]["cell_dots"])
    out = cc.decode_patch(scan, e, soft=False, diagnostics=False)
    err = out["err_map"]
    gtb = out["gt_cells"].astype(bool)
    pred = out["gt_cells"] ^ err.astype(np.uint8)
    u = np.zeros_like(gtb)
    for p in "CMY":
        if p == plane:
            continue
        sib = cc.load_gt(cc.entry(manifest, f"{field}_{p}"))
        u |= sib[::cell_dots, ::cell_dots].astype(bool)[: gtb.shape[0], : gtb.shape[1]]
    return {
        "patch": f"{field}_{plane}", "plane": plane, "channel": out["channel"],
        "cell_dots": cell_dots, "ber": out["ber"], "n_cells": out["cells"],
        "mi_bits_hard": _hard_mi_bits(out["gt_cells"], pred),
        "null_ber": out["ber_null"], "null_ok": out["null_ok"],
        "warp_windows_used": out["warp_windows_used"],
        "warp_windows_total": out["warp_windows_total"],
        "split_other_ink": {
            "err_overlap": acp._split(err, u), "err_clear": acp._split(err, ~u),
            "miss_overlap": acp._split(err, gtb & u),
            "miss_clear": acp._split(err, gtb & ~u),
            "fa_overlap": acp._split(err, ~gtb & u),
            "fa_clear": acp._split(err, ~gtb & ~u)},
    }


def rigid_unmix_decode(scan: dict, wm: dict, manifest: dict, field: str,
                       a_cmy: np.ndarray) -> dict:
    """Unmixed-density decode of a 3-plane composite (the 002.0/002.1 TODO).

    Per plane p: rigid GT lock in p's own channel (patch_view), per-cell
    r/g/b density means on p's lattice, t = A_cmy^-1 @ D per cell, blind
    median threshold on t_p. The raw-channel decode on the SAME registration
    and threshold rule is reported alongside (alignment-method control)."""
    a_inv = np.linalg.inv(a_cmy)
    out: dict = {"A_cmy": a_cmy.tolist(),
                 "threshold": "blind per-field median (50% fields)"}
    for i, p in enumerate("CMY"):
        e = cc.entry(manifest, f"{field}_{p}")
        cell_dots = int(e["params"]["cell_dots"])
        v = cc.patch_view(scan, e)
        D = {}
        for ch in ("r", "g", "b"):
            m = np.asarray(cc.cell_means(v, cell_dots, ch), np.float64)
            ny, nx = m.shape
            xg, yg = np.meshgrid(
                e["x_dots"] + (np.arange(nx) + 0.5) * cell_dots,
                e["y_dots"] + (np.arange(ny) + 0.5) * cell_dots)
            w = np.maximum(cc.white_at(wm, xg, yg, ch), 1e-3)
            D[ch] = -np.log10(np.maximum(m, 1.0) / w)
        Dv = np.stack([D["r"], D["g"], D["b"]], axis=-1)
        t = Dv @ a_inv.T
        tp = t[..., i]
        gc = cc.gt_cells(e)[: tp.shape[0], : tp.shape[1]]
        d_own = D[PRIMARY_CHANNEL[p]]
        bits_raw = (d_own > np.median(d_own)).astype(np.uint8)
        bits_um = (tp > np.median(tp)).astype(np.uint8)
        rec_raw = cc.ber_with_null(bits_raw, gc)
        rec_um = cc.ber_with_null(bits_um, gc)
        out[p] = {"lock_q": v.local_quality, "locked": bool(v.local_locked),
                  "raw_rigid": {**rec_raw,
                                "mi_bits_hard": _hard_mi_bits(gc, bits_raw)},
                  "unmixed": {**rec_um,
                              "mi_bits_hard": _hard_mi_bits(gc, bits_um)}}
    return out


def block_a(scan: dict, manifest: dict, wm: dict, a_cmy: np.ndarray) -> dict:
    # --- alphabet fields ------------------------------------------------------
    fields_spec = [("A1/state7_c3", "CMY"), ("A1/state7_c4", "CMY"),
                   ("A1/state7_c6", "CMY"), ("A2/state8k_c4", "CMYK")]
    alphabet: dict[str, dict] = {}
    for field, planes in fields_spec:
        print(f"alphabet field {field} ...", flush=True)
        rec = measure_alphabet_field(scan, wm, field, planes)
        alphabet[field] = rec
        best7 = rec["best_uniform_subsets"].get(str(min(7, rec["n_states"])))
        print(f"  {field}: acc={rec['accuracy']:.4f} "
              f"MI={rec['mi_bits_uniform']:.3f} cap={rec['capacity_bits']:.3f} "
              f"null_ok={rec['null']['null_ok']} "
              f"(best-{min(7, rec['n_states'])} {best7['mi_bits']:.3f})",
              flush=True)
        _free_f32(scan)

    # c3 stationarity vs 002.0 (different sheet, same construction — the
    # 002.0 number is the best-7 SUBSET of the printed 8-state field; here the
    # 7-state alphabet is printed directly, no CMY cells on paper at all)
    mi_c3 = alphabet["A1/state7_c3"]["mi_bits_uniform"]
    delta = mi_c3 - ANCHORS_002_0["best7_c3"]
    stationarity = {
        "measured_mi7_c3": mi_c3,
        "anchor_best7_c3_002_0": ANCHORS_002_0["best7_c3"],
        "anchor_uniform8_c3_002_0": ANCHORS_002_0["mi8_c3_uniform"],
        "anchor_capacity8_c3_002_0": ANCHORS_002_0["cap8_c3"],
        "delta_bits": float(delta),
        "tol_bits": STATIONARITY_TOL_BITS,
        "replicates": bool(abs(delta) <= STATIONARITY_TOL_BITS),
        "note": "tolerance = within-page position variance scale from 002.0 "
                "(same-construction replicas ~1 pp BER apart); construction "
                "difference stated: 002.0 best-7 is a subset computation on a "
                "printed 8-state field, this is a printed 7-state field",
    }

    # --- binary composites c4/c6: v4 raw-channel + rigid unmix ---------------
    composites: dict[str, dict] = {}
    for field in ("A3/comp_c4", "A3/comp_c6"):
        print(f"composite {field} (v4 + unmix) ...", flush=True)
        planes = {p: decode_composite_plane(scan, manifest, field, p)
                  for p in "CMY"}
        unmix = rigid_unmix_decode(scan, wm, manifest, field, a_cmy)
        for p in "CMY":
            print(f"  {field}_{p}: v4 ber={planes[p]['ber']:.4f} "
                  f"(null {planes[p]['null_ber']:.3f}) "
                  f"rigid raw={unmix[p]['raw_rigid']['ber']:.4f} "
                  f"unmixed={unmix[p]['unmixed']['ber']:.4f}", flush=True)
        composites[field] = {"v4_raw_channel": planes, "rigid_unmix": unmix}
        _free_f32(scan)

    # --- same-sheet clean mask refs -------------------------------------------
    refs: dict[str, dict] = {}
    print("A4 clean mask refs ...", flush=True)
    for name in ("A4/ref_C_c4", "A4/ref_M_c4", "A4/ref_Y_c4",
                 "A4/ref_K_c4", "A4/ref_K_c6"):
        out = cc.decode_patch(scan, name, soft=False, diagnostics=False)
        pred = out["gt_cells"] ^ out["err_map"].astype(np.uint8)
        e = cc.entry(manifest, name)
        refs[name] = {"ber": out["ber"], "null_ber": out["ber_null"],
                      "null_ok": out["null_ok"], "channel": out["channel"],
                      "cell_dots": int(e["params"]["cell_dots"]),
                      "n_cells": out["cells"],
                      "mi_bits_hard": _hard_mi_bits(out["gt_cells"], pred)}
        print(f"  {name}: ber={out['ber']:.4f} null={out['ber_null']:.3f} "
              f"MI={refs[name]['mi_bits_hard']:.3f}", flush=True)
    _free_f32(scan)

    # --- screen tax vs cell size ----------------------------------------------
    print("screen-tax spectra (Block A, cell-aware lattice) ...", flush=True)
    cache: dict = {}
    tax: dict[str, dict] = {}
    spec_names = ([f"A1/state7_c{c}_{p}" for c in (3, 4, 6) for p in "CMY"]
                  + [f"A2/state8k_c4_{p}" for p in "CMYK"]
                  + [f"A3/comp_c{c}_{p}" for c in (4, 6) for p in "CMY"]
                  + ["A4/ref_C_c4", "A4/ref_M_c4", "A4/ref_Y_c4",
                     "A4/ref_K_c4", "A4/ref_K_c6"])
    for nm in spec_names:
        d = screening_field_cell(scan, nm, cache)
        d["family_tax_db"] = {
            fam: d["family_excess_db"][fam] - d["family_gt_floor_db"][fam]
            for fam in acp.SCREEN_FAMILIES}
        tax[nm] = d
    return {"alphabet_fields": alphabet, "c3_stationarity": stationarity,
            "composites": composites, "refs": refs, "screen_tax": tax}


# ---------------------------------------------------------------------------
# bottom line: bits/cell for every measured configuration on this engine
# ---------------------------------------------------------------------------

def bottom_line(block_a_res: dict) -> list[dict]:
    rows: list[dict] = []

    def add(config: str, cell_dots: int, bits_per_cell: float, source: str,
            derived: bool = False) -> None:
        rows.append({"config": config, "cell_dots": cell_dots,
                     "bits_per_cell": float(bits_per_cell),
                     "bits_per_mm2": float(bits_per_cell
                                           * _cells_per_mm2(cell_dots)),
                     "source": source, "derived": derived})

    for p in "KCMY":  # clean single-plane binary c3 (002.0, cross-sheet)
        add(f"clean single-plane {p} binary", 3,
            ANCHORS_002_0["clean_c3_mi"][p],
            "002.0 CAL-1 (cross-sheet anchor)")
    refs = block_a_res["refs"]
    for p in "CMYK":  # clean single-plane binary c4 (this sheet)
        add(f"clean single-plane {p} binary", 4,
            refs[f"A4/ref_{p}_c4"]["mi_bits_hard"], "this sheet, A4 mask ref")
    add("clean single-plane K binary", 6, refs["A4/ref_K_c6"]["mi_bits_hard"],
        "this sheet, A4 mask ref")

    alpha = block_a_res["alphabet_fields"]
    for field, label in (("A1/state7_c3", "screened 7-state alphabet"),
                         ("A1/state7_c4", "screened 7-state alphabet"),
                         ("A1/state7_c6", "screened 7-state alphabet"),
                         ("A2/state8k_c4", "screened 8-state {7+K} alphabet")):
        rec = alpha[field]
        add(f"{label} (uniform)", rec["cell_dots"], rec["mi_bits_uniform"],
            "this sheet, QDA MI")
        add(f"{label} (BA capacity)", rec["cell_dots"], rec["capacity_bits"],
            "this sheet, BA on QDA confusion", derived=True)

    # screened binary composite c3 (002.0 BER anchors -> BSC MI, derived)
    mi_c3 = sum(_mi_bsc_bits(b) for b in
                ANCHORS_002_0["composite_c3_ber"].values())
    add("screened binary composite CMY (sum, raw channels)", 3, mi_c3,
        "002.0 composite BER -> 1-H2 (cross-sheet, derived)", derived=True)
    for field, cell in (("A3/comp_c4", 4), ("A3/comp_c6", 6)):
        comp = block_a_res["composites"][field]
        raw_sum = sum(comp["v4_raw_channel"][p]["mi_bits_hard"] for p in "CMY")
        um_sum = sum(comp["rigid_unmix"][p]["unmixed"]["mi_bits_hard"]
                     for p in "CMY")
        add("screened binary composite CMY (sum, raw channels)", cell,
            raw_sum, "this sheet, v4 hard MI")
        add("screened binary composite CMY (sum, unmixed)", cell,
            um_sum, "this sheet, rigid unmix decode")
    return rows


# ---------------------------------------------------------------------------
# results draft
# ---------------------------------------------------------------------------

def write_results_draft(rep: dict, path: Path) -> None:
    bb, ba_ = rep["blockB"], rep["blockA"]
    reg = rep["registration"]
    an1 = ANCHORS_002_1
    L: list[str] = []
    a = L.append
    a("<!-- draft completion of the 002.2 RESULTS entry; paste below the run "
      "header table in experiments/002-calibration-page.md -->")
    a("")
    a("| scan | `scans/test-scan-overlap2.png` RGBA 1200 dpi, 0°, sha256 "
      f"`{rep['scan']['sha256']}` |")
    a("| analyzer | `analyze_overlap2.py` → `build/overlap2_report.json` "
      f"({rep['elapsed_s']:.0f} s); discriminators + gates imported unchanged "
      "from `analyze_composite_probe.py` (002.1), QDA/MI from `cal_color.py` |")
    n_nulls = rep["null_controls"]["n_total"]
    fails = rep["null_controls"]["failures"]
    a(f"| discipline | identical parameters across S1–S3 and across c3/c4/c6; "
      f"{n_nulls} null controls ({'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}); "
      "cross-sheet anchors marked as such |")
    a("")
    a(f"Registration: {reg['n_landmarks_used']}/{reg['n_landmarks_total']} "
      f"landmarks (4 chiral corners + 63 plus marks), residual RMS "
      f"{reg['residual_rms_dots']:.2f} dots (max {reg['residual_max_dots']:.2f}), "
      f"rot {reg['rotation_deg']:.3f}°, px/dot {reg['px_per_dot_x']:.5f}/"
      f"{reg['px_per_dot_y']:.5f}; ruler_check reports the expected KeyError "
      "(no rulers on this page).")
    a("")
    a("#### Block B — S-variant verdict (002.1 decision rule, same gates)")
    a("")
    a("| variant | screened beyond A4 bar | worst miss@ovl / clear | CM solid "
      "r-med (presC-D) | max BER Δ vs 002.1 P4 c3 (C/M/Y) | qualifies |")
    a("|---|---|---|---|---|---|")
    for vid in S_VARIANTS:
        vv = bb["variants"][vid]
        worst = max((bb["fields"][nm]["split_under"]["miss_overlap"]["err"],
                     bb["fields"][nm]["split_under"]["miss_clear"]["err"])
                    for nm in bb["fields"] if nm.startswith(vid + "/")
                    and "split_under" in bb["fields"][nm])
        sol = bb["solids"][vid]
        dd = vv["ber_delta_vs_002_1_P4"]
        by_p = {p: max(d for nm, d in dd.items()
                       if bb["fields"][nm]["plane"] == p) for p in "CMY"}
        scr = (", ".join(vv["screened_beyond_A4"]) or "clean").replace("|", "·")
        a(f"| {vid} | {scr} | {worst[0]:.3f} / {worst[1]:.3f} | "
          f"{sol['median_raw_rgb']['r']:.1f} "
          f"({sol['presence_C_under_M_density']:+.2f}) | "
          f"{by_p['C']:+.3f}/{by_p['M']:+.3f}/{by_p['Y']:+.3f} | "
          f"{vv['qualifies']} |")
    a("")
    a(f"Anchors (002.1 sheet, same scanner+day, CROSS-SHEET): CM-solid r-median "
      f"knockout {an1['solid_r_median']['knockout_CM_lo']:.0f}–"
      f"{an1['solid_r_median']['knockout_CM_hi']:.0f}, overlap-preserved (P0) "
      f"{an1['solid_r_median']['P0_CM']:.1f}, C100 "
      f"{an1['solid_r_median']['C100']:.1f}, M100 "
      f"{an1['solid_r_median']['M100']:.1f}; P4 c3 refs BER C "
      f"{an1['p4_ref_ber_c3']['C']:.4f} / M {an1['p4_ref_ber_c3']['M']:.4f} / "
      f"Y {an1['p4_ref_ber_c3']['Y']:.4f}.")
    a(f"A4 clean-ref screening bar (this sheet): "
      f"{bb['decision']['A4_baseline_screened_fc']}. NOTE (verify pass): the "
      "212|r entry in this bar is a CELL-LATTICE ALIAS, not a device screen — "
      "the 212-lpi family point (0.25, 0.25) cyc/dot is a c4 lattice bin, and "
      "the A4 refs are c4. The S fields are c3 (all three families "
      "off-lattice), so S-variant judgments are unaffected; S3's 212|r "
      "(21.2 dB) is real screen structure swallowed by the aliased bar — it "
      "does not change any verdict (S3 is screened via 165|rg + 212|gb).")
    a(f"Decision: adopted = **{bb['decision']['adopted']}**. S1 = S2 = "
      "knockout + re-screen (the 002.1 P1–P3 failure, now reproduced in "
      "Separation color spaces; setoverprint/OPM again without effect). S3 "
      "reproduces the P0 channel almost exactly (solid r-median 49.8 vs P0 "
      "49.5, presC +0.55 vs +0.56; field BERs within ~2.8 pp of the P0 "
      "anchors): DeviceN-image = put_cmyk_bitmap, one more emission path "
      "with the same RIP behavior, not a new channel.")
    a("")
    a("#### Block A — alphabet sweep (screened cmyk-image path)")
    a("")
    a("| field | cell | states | acc | MI uniform | BA capacity | best-subset "
      "(same size as 002.0 comparisons) | null ok |")
    a("|---|---|---|---|---|---|---|---|")
    for field, rec in ba_["alphabet_fields"].items():
        k = str(rec["n_states"])
        bs = rec["best_uniform_subsets"][k]
        a(f"| {field} | c{rec['cell_dots']} | {rec['n_states']} | "
          f"{rec['accuracy']:.3f} | {rec['mi_bits_uniform']:.3f} | "
          f"{rec['capacity_bits']:.3f} | {bs['mi_bits']:.3f} "
          f"({{{','.join(bs['states'])}}}) | {rec['null']['null_ok']} |")
    st = ba_["c3_stationarity"]
    a("")
    a(f"c3 stationarity: measured 7-state c3 MI {st['measured_mi7_c3']:.3f} vs "
      f"002.0's best-7 {st['anchor_best7_c3_002_0']:.3f} "
      f"(Δ {st['delta_bits']:+.3f}, tol ±{st['tol_bits']:.2f}) → "
      f"{'replicates' if st['replicates'] else 'DOES NOT replicate'}. "
      "(002.0's number is a subset computation on a printed 8-state field; "
      "here the 7-state alphabet is printed directly.)")
    a("")
    a("#### Composites c4/c6 — raw channel vs unmixed (crosstalk matrix "
      "applied; the 002.0/002.1 TODO)")
    a("")
    a("| field | plane | v4 raw BER | rigid raw BER | unmixed BER | v4 MI | "
      "unmixed MI | same-sheet clean ref BER (c4) |")
    a("|---|---|---|---|---|---|---|---|")
    for field in ("A3/comp_c4", "A3/comp_c6"):
        comp = ba_["composites"][field]
        for p in "CMY":
            v4 = comp["v4_raw_channel"][p]
            um = comp["rigid_unmix"][p]
            ref = ba_["refs"][f"A4/ref_{p}_c4"]["ber"]
            a(f"| {field} | {p} | {v4['ber']:.4f} | "
              f"{um['raw_rigid']['ber']:.4f} | {um['unmixed']['ber']:.4f} | "
              f"{v4['mi_bits_hard']:.3f} | {um['unmixed']['mi_bits_hard']:.3f} "
              f"| {ref:.4f} |")
    a("")
    a("002.0 c3 composite anchors (cross-sheet): C 8.8% / M 11.8% / Y 24.0%.")
    a("")
    a("#### Screen tax vs cell size (family disk excess − own GT floor, dB)")
    a("")
    a("| patch | ch | 165 lpi | 212 lpi¹ | 224 lpi² |")
    a("|---|---|---|---|---|")
    for nm, d in ba_["screen_tax"].items():
        t = d["family_tax_db"]
        a(f"| {nm} | {d['channel']} | {t['165lpi_pm14deg']:.1f} | "
          f"{t['212lpi_45deg']:.1f} | {t['224lpi_pm27deg']:.1f} |")
    a("")
    a("¹ 212-family readings on c4 patches are cell-lattice-aliased "
      "((0.25, 0.25) cyc/dot is a c4 lattice bin) — discount them. "
      "² 224-family readings on c6 patches likewise ((1/3, 1/6) is a c6 "
      "lattice bin). The 165 family is off-lattice at c3, c4 AND c6.")
    a("")
    a("Reading: the 165-lpi screen tax does NOT shrink with cell size "
      "(13–21 dB at every cell size, all planes) — the RIP screen structure "
      "persists; what improves is the DECODE, which averages more screen "
      "periods per cell (7-state acc 0.72 → 0.84 → 0.99, MI 1.48 → 1.98 → "
      "2.76 across c3/c4/c6).")
    a("")
    a("#### Bottom line — bits/cell on this engine (input to the modulation "
      "decision)")
    a("")
    a("| configuration | cell | bits/cell | bits/mm² | source |")
    a("|---|---|---|---|---|")
    for r in rep["bottom_line_bits_per_cell"]:
        a(f"| {r['config']} | c{r['cell_dots']} | {r['bits_per_cell']:.3f} | "
          f"{r['bits_per_mm2']:.1f} | {r['source']} |")
    a("")
    a("#### Caveats (facts, not editorializing)")
    a("")
    a("- QDA MI values carry the cal_color interleaved-fold optimism bias "
      "(spatially adjacent cells in train and test); comparisons across cell "
      "sizes/fields share the bias, absolute values are upper-ish.")
    a("- Field-to-field spread on ONE sheet is large: the best-7 subset MI "
      "inside A2/state8k_c4 reads 2.208 vs the printed A1/state7_c4 field's "
      "1.980 — same alphabet, same cell size, same sheet → ~±0.2 bits "
      "position/field variance at c4. The c3-vs-002.0 delta (−0.41) exceeds "
      "this scale but must be read against it; the c3 per-plane BERs "
      "(C 11.1 / M 14.7 / Y 27.0%) are uniformly worse than 002.0's "
      "composite c3 (8.8/11.8/24.0) — a real channel/position difference, "
      "not an analysis artifact (all warp locks 98–242/242, nulls pass).")
    a("- A2 {7+K} with the K-aligned grey density added as a 4th feature: "
      "MI 2.364 (acc 0.904) vs 2.074 on 3 features; the 3-feature BA "
      "capacity puts ZERO weight on K (best-7 2.208). K earns its 8th-"
      "symbol place only if the decoder measures a grey/K feature.")
    a("- BA capacity and best-subset numbers are computed ON the QDA confusion "
      "— they inherit that optimism and assume the confusion is the channel.")
    a("- Single sheet, single scan, day-1 numbers (printed+scanned "
      "2026-07-04); no aging, no hygro cycle, one page position per config.")
    a("- Block B BER bar is CROSS-SHEET (002.1 P4 refs; this sheet has no c3 "
      "single-plane refs) — same scanner+day, but sheet-to-sheet variance is "
      "not separated. Solids anchors likewise cross-sheet.")
    a("- Y-plane numbers through the screened path remain crosstalk-inflated "
      "on the raw b channel and entangled with the pre-existing Y 224-lpi "
      "texture (002.1 finding 2); unmixed decode addresses the crosstalk "
      "part only.")
    a("- lpr -o raw transport (scratch-sheet precedent 002.0/002.1); port "
      "9100 remains canonical for data sheets.")
    path.write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def collect_null_controls(rep: dict) -> dict:
    """Roll up every null control in the report; list failures by path."""
    entries: list[tuple[str, bool]] = []
    for nm, f in rep["blockB"]["fields"].items():
        entries.append((f"blockB/{nm}", bool(f["null_ok"])))
    for field, rec in rep["blockA"]["alphabet_fields"].items():
        entries.append((f"blockA/{field}/classifier", bool(rec["null"]["null_ok"])))
        for p, s in rec["per_plane_decode"].items():
            if s.get("null_ok") is not None:
                entries.append((f"blockA/{field}/{p}", bool(s["null_ok"])))
        if "variant_4d" in rec:
            entries.append((f"blockA/{field}/4d",
                            bool(rec["variant_4d"]["null"]["null_ok"])))
    for field, comp in rep["blockA"]["composites"].items():
        for p in "CMY":
            entries.append((f"blockA/{field}/{p}/v4",
                            bool(comp["v4_raw_channel"][p]["null_ok"])))
            for tag in ("raw_rigid", "unmixed"):
                entries.append((f"blockA/{field}/{p}/{tag}",
                                bool(comp["rigid_unmix"][p][tag]["null_ok"])))
    for nm, r_ in rep["blockA"]["refs"].items():
        entries.append((f"blockA/{nm}", bool(r_["null_ok"])))
    failures = [nm for nm, ok in entries if not ok]
    return {"n_total": len(entries), "failures": failures}


def analyze(scan_path: Path) -> dict:
    t0 = time.time()
    manifest = cc.load_manifest(MANIFEST_PATH)

    # construction invariant: S1-S3 paint byte-identical per-plane content
    ident = {}
    for base in ("field_cm_C", "field_cm_M", "field_cmy_C", "field_cmy_M",
                 "field_cmy_Y", "solid_cm_C", "solid_cm_M"):
        a1 = cc.load_gt(cc.entry(manifest, f"S1/{base}"))
        ident[base] = all(np.array_equal(
            a1, cc.load_gt(cc.entry(manifest, f"S{v}/{base}"))) for v in "23")
    if not all(ident.values()):
        raise AssertionError(f"per-plane GT differs across S variants: {ident}")

    print(f"loading + registering {scan_path}", flush=True)
    scan = cc.load_scan(scan_path)
    sha_ok = scan["sha256"] == EXPECTED_SCAN_SHA256
    if not sha_ok:
        print(f"!! scan sha256 {scan['sha256']} != expected", flush=True)
    reg = cc.register(scan, manifest)
    rms = reg["residual_rms_dots"]
    print(f"  {scan['kind']}, {reg['n_landmarks_used']}/"
          f"{reg['n_landmarks_total']} landmarks, residual RMS {rms:.3f} dots "
          f"(max {reg['residual_max_dots']:.3f}), rot {reg['rotation_deg']:.3f}°, "
          f"px/dot {reg['px_per_dot_x']:.5f}/{reg['px_per_dot_y']:.5f}",
          flush=True)
    if rms is None or rms >= acp.REG_RMS_GATE_DOTS:
        raise cc.RegistrationError(
            f"residual RMS {rms} >= {acp.REG_RMS_GATE_DOTS}")

    print("white model ...", flush=True)
    wm = cc.white_model(scan)

    bb = block_b(scan, manifest, wm)
    _free_f32(scan)

    # measured crosstalk matrix (002.0 CAL-1, calpage_report channel_params)
    calpage_rep = cc.load_manifest(cc.BUILD / "calpage_report.json")
    xtalk = calpage_rep["channel_params"]["crosstalk_matrix"]
    a_cmy = np.array(xtalk["A_density_per_unit_ink"], np.float64)[:, :3]

    ba_res = block_a(scan, manifest, wm, a_cmy)

    rep: dict = {
        "run": "002.2",
        "analyzer": "analyze_overlap2.py",
        "scan": {"path": str(scan_path), "sha256": scan["sha256"],
                 "sha256_expected": EXPECTED_SCAN_SHA256, "sha256_ok": sha_ok,
                 "kind": scan["kind"], "shape_px": list(scan["grey"].shape)},
        "manifest": {"path": str(MANIFEST_PATH), "jobid": manifest["jobid"],
                     "seed": manifest["seed"],
                     "ps_sha256": manifest["ps_sha256"]},
        "registration": reg,
        "gates": {"registration_rms_dots": rms,
                  "screen_strong_db": acp.SCREEN_STRONG_DB,
                  "screen_coherent_db": acp.SCREEN_COHERENT_DB,
                  "knockout_miss_gate": acp.KNOCKOUT_MISS_GATE,
                  "knockout_miss_ratio": acp.KNOCKOUT_MISS_RATIO,
                  "presence_knockout_max": acp.PRESENCE_KNOCKOUT_MAX,
                  "presence_preserved_min": acp.PRESENCE_PRESERVED_MIN,
                  "ber_gate_abs": BER_GATE_ABS,
                  "stationarity_tol_bits": STATIONARITY_TOL_BITS,
                  "provenance": "all gates identical to 002.1 "
                                "(analyze_composite_probe constants)"},
        "anchors": {"002.0": ANCHORS_002_0, "002.1": ANCHORS_002_1},
        "crosstalk_matrix_A_cmy": a_cmy.tolist(),
        "gt_identity_S1_S3": ident,
        "blockB": bb,
        "blockA": ba_res,
    }
    rep["bottom_line_bits_per_cell"] = bottom_line(ba_res)
    rep["null_controls"] = collect_null_controls(rep)
    rep["elapsed_s"] = round(time.time() - t0, 1)
    cc.save_report(rep, OUT_REPORT)
    write_results_draft(rep, OUT_DRAFT)

    # ---- human summary ------------------------------------------------------
    print("\n== BLOCK B VERDICT (002.1 rule) ==")
    for vid in S_VARIANTS:
        vv = bb["variants"][vid]
        scr = ", ".join(vv["screened_beyond_A4"]) or "clean"
        print(f"{vid}: screen_beyond_A4=[{scr}] solid={vv['solid_verdict']} "
              f"knockout_free={vv['knockout_free']} "
              f"ber_ok={vv['ber_within_gate']} -> qualifies={vv['qualifies']}")
    print(f"adopted: {bb['decision']['adopted']}")
    print("\n== BLOCK A ALPHABET ==")
    for field, rec in ba_res["alphabet_fields"].items():
        print(f"{field} c{rec['cell_dots']}: MI={rec['mi_bits_uniform']:.3f} "
              f"cap={rec['capacity_bits']:.3f} acc={rec['accuracy']:.3f}")
    st = ba_res["c3_stationarity"]
    print(f"c3 stationarity: {st['measured_mi7_c3']:.3f} vs "
          f"{st['anchor_best7_c3_002_0']:.3f} (Δ{st['delta_bits']:+.3f}) "
          f"replicates={st['replicates']}")
    print("\n== BOTTOM LINE (bits/cell | bits/mm²) ==")
    for r in rep["bottom_line_bits_per_cell"]:
        print(f"  c{r['cell_dots']} {r['config']:55s} "
              f"{r['bits_per_cell']:6.3f} | {r['bits_per_mm2']:6.1f}  "
              f"[{r['source']}]")
    nc = rep["null_controls"]
    print(f"\nnull controls: {nc['n_total']} total, "
          f"failures: {nc['failures'] or 'none'}")
    print(f"report -> {OUT_REPORT}\ndraft  -> {OUT_DRAFT}  "
          f"({rep['elapsed_s']:.0f} s)")
    return rep


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="002.2 overlap2 analyzer")
    ap.add_argument("scan", nargs="?", default=str(DEFAULT_SCAN))
    args = ap.parse_args()
    analyze(Path(args.scan))

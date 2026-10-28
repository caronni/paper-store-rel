#!/usr/bin/env python
"""analyze_modprobe.py — experiment 003.0: modulation probes, one scan.

Measures the four H1-H4 inputs of experiments/003-modulation-probes.md from
scans/test-scan-modprobe.png against build/modprobe_manifest.json + GT:

H1 (headline) — screening trigger on dot-disjoint multi-plane emission:
  canary-A screening spectra (002.1 machinery, gates unchanged) for D1 (mask
  pair), D2 (13,225 per-cell masks), D3 (cmyk control), D4 (single-plane
  control), D5 (5-state, 4 disjoint masks), D6 (5-state cmyk); clean bar =
  same-sheet single-plane imagemask patches (D4 + K4 + S1) plus the
  CROSS-SHEET Y-plane b-channel families of 002.1 (this sheet has no
  single-plane Y ref). Per-plane BER (v4 dense-warp means + fixed-rate
  threshold at the construction prior) with GT-aware null controls, crosstalk
  splits by sibling-plane GT (the knockout split is vacuous at dot level by
  construction — dot-disjoint emission has no overlap cells), and the D5-vs-D6
  5-state QDA confusion/MI head-to-head (cal_color machinery).

H2 — white-void C subchannel: S1-vs-S2 K dot-BER paired per dot (identical K
  field), near-mark vs far-field miss split (same split on S1 = control),
  b-channel blindness check, C-mark recovery via a chroma statistic
  s = D_r - max(D_g, D_b) thresholded on the S1 same-coordinates null
  (+ shifted-coordinate null), screening spectra S2 vs S1, and the S3
  colored-pilot demo (pilot recovery, data-cell BER vs the same-sheet
  K4/encode_c3 anchor, chroma separability margins).

H3 — 2-D RLL constrained K fields at the dot grid: per-dot v4 decode
  (dense warp, 2 scan px/dot, local-background + fixed-rate threshold at the
  manifest ink fraction), run-survival statistics vs GT (where do 2- and
  3-runs die), achievable-rate proxy sampler_entropy x (1 - H2(dotBER))
  (ISI-correlated errors -> estimate pending trellis detection, M2), vs the
  same-sheet c2/c3 incumbents (decode_patch v4, 001/002-comparable).

H4 — motif survival library: per-motif (12 x 132 instances) survival rate,
  ink-flux response, centroid shift, per-instance variance ->
  build/motif_library.json (trellis branch-metric calibration data).

Discipline (001.2): every BER/recovery measurement carries a null control;
for structured or asymmetric-prior fields the null is judged against the
EXPECTED level computed from the GT itself (an 8-shift null of a 1/5-ink
plane is 0.32, not 0.50 — the 0.50 gate would be a false alarm). No
per-patch parameter tuning: one threshold rule (local-median residual +
quantile at the construction prior), one detection rule, one clearance rule,
stated once. Spectra gates identical to 002.1/002.2 (imported, not copied).

Determinism: no randomness anywhere in this module.

Run (repo root, ~6-10 min):
  env/bin/python experiments/003-modulation-probes/analyze_modprobe.py \
      scans/test-scan-modprobe.png
Outputs: build/modprobe_report.json, build/motif_library.json,
build/RESULTS-003.0-draft.md, human summary on stdout.
"""
from __future__ import annotations

import hashlib
import math
import sys
import time
from pathlib import Path

import numpy as np
from scipy import ndimage

_HERE = Path(__file__).resolve().parent
_EXP002 = _HERE.parent / "002-calibration-page"
for _p in (str(_HERE), str(_EXP002)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import analyze_composite_probe as acp  # noqa: E402  (002.1 spectra/gates — reused verbatim)
import analyze_overlap2 as ao2  # noqa: E402        (002.2 cell-aware spectra, BA, subsets)
import cal_color as ccol  # noqa: E402              (QDA/MI machinery — reused verbatim)
import cal_core as cc  # noqa: E402                 (analyzer core; per-manifest GT base dir)
import scanlab  # noqa: E402                        (v4 decode primitives, exp 001)

REPO = _HERE.parent.parent
BUILD = _HERE / "build"
MANIFEST_PATH = BUILD / "modprobe_manifest.json"
DEFAULT_SCAN = REPO / "scans" / "test-scan-modprobe.png"
EXPECTED_SCAN_SHA256 = ("a5de3fe82e2dc2baf89557bf2fa74c906ab094773c"
                        "6a361fd29877773049e963")
EXPECTED_MANIFEST_SHA256 = ("c7fcdb6e0413db26eb6bb823a03212624f6156b4"
                            "ac1d5b4da243e2d1ce96c445")
OUT_REPORT = BUILD / "modprobe_report.json"
OUT_DRAFT = BUILD / "RESULTS-003.0-draft.md"
OUT_MOTIF = BUILD / "motif_library.json"

CELL_DOTS = 3
DOTS_PER_MM2 = (cc.HW_DPI / 25.4) ** 2          # 557.9 areal dots / mm^2
SHIFT_DOTS = 8                                   # null-control shift (001.2)
NULL_TOL = 0.02
MED_SIZE = 31            # local-background median window (dots or cells)
BER_GATE_ABS = acp.BER_GATE_ABS                  # 002.1 rule: ref + 0.02
SURVIVAL_FLUX_MIN = 0.5  # motif 'survived' rule (stated once, all motifs)
MARK_THR_SIGMA = 4.0     # C-mark threshold: S1-null median + 4 robust sigma

# same-sheet clean screening bar (single-plane imagemask patches) + the
# CROSS-SHEET b-channel bar: this sheet has no single-plane Y ref, and 002.1
# measured the Y-plane imagemask texture as P4-baseline {165|b, 224|b}.
BASELINE_PATCHES: tuple[tuple[str, int], ...] = (
    ("D4_C", 3), ("D4_M", 3), ("K4/encode_c2", 2), ("K4/encode_c3", 3),
    ("S1", 1))
CROSS_SHEET_B_BAR: tuple[str, ...] = ("165lpi_pm14deg|b", "224lpi_pm27deg|b")

D_EMISSIONS: dict[str, tuple[str, ...]] = {
    "D1": ("D1_C", "D1_M"),
    "D2": ("D2_C", "D2_M"),
    "D3": ("D3_C", "D3_M"),
    "D4": ("D4_C", "D4_M"),
    "D5": ("D5_C", "D5_M", "D5_Y", "D5_K"),
    "D6": ("D6_C", "D6_M", "D6_Y", "D6_K"),
}
D_PRIOR_INK: dict[str, float] = {"D1": 1 / 3, "D2": 1 / 3, "D3": 1 / 3,
                                 "D4": 1 / 3, "D5": 1 / 5, "D6": 1 / 5}

# cross-sheet anchors (same engine; sheet-to-sheet variance NOT separated)
ANCHORS: dict = {
    "002.0": {"clean_c3_ber": {"K": 0.0374, "C": 0.0357, "M": 0.0381,
                               "Y": 0.0718},
              "k_c2_hard_ber": 0.131,
              "mi8_c3_uniform": 1.757, "best7_c3": 1.890},
    "002.1": {"p4_ref_ber_c3": {"C": 0.0448, "M": 0.0455, "Y": 0.0827},
              "p4_baseline_screened_fc": ["165lpi_pm14deg|b",
                                          "224lpi_pm27deg|b"],
              "screened_families_db": "165(+212) at 20-28 dB, clean 9-12 dB"},
    "002.2": {"state7_c3_mi": 1.479, "state7_c3_acc": 0.724,
              "best5_subset_c3_mi": 1.372,
              "best5_subset_c3": ["W", "C", "M", "CY", "MY"],
              "state7_c4_mi": 1.980, "state8k_c4_mi": 2.074},
    "note": "cross-sheet, same engine+scanner; 002.x measured same-sheet "
            "position variance ~1 pp BER / ~0.2 bits MI at c4",
}


def _h2_bits(p: float) -> float:
    """Binary entropy H2(p) in bits."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return float(-p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p))


def mi_hard_bits(gt_bits: np.ndarray, bits: np.ndarray) -> float:
    """Hard-decision MI from the 2x2 confusion (cal_color counting)."""
    conf = ccol._confusion(gt_bits.ravel().astype(np.int64),
                           bits.ravel().astype(np.int64), 2)
    return ccol._mi_bits_from_counts(conf)


def ber_with_gt_null(bits: np.ndarray, gt_bits: np.ndarray,
                     shift: int = SHIFT_DOTS) -> dict:
    """BER + shifted-GT null judged against the EXPECTED null level computed
    from the GT itself (2p(1-p)-scale for asymmetric priors, autocorrelation
    for RLL fields — the flat 0.50 gate only holds for i.i.d. 50% fields)."""
    b = bits.astype(bool)
    g = gt_bits.astype(bool)
    gs = np.roll(g, shift, axis=1)
    null = float((b != gs).mean())
    exp = float((g != gs).mean())
    return {"ber": float((b != g).mean()), "n": int(b.size),
            "ber_null": null, "null_expected_from_gt": exp,
            "null_ok": bool(abs(null - exp) <= NULL_TOL),
            "shift": shift}


def fixed_rate_bits(means: np.ndarray, p_ink: float,
                    med_size: int = MED_SIZE) -> np.ndarray:
    """One threshold rule for every field (no per-patch tuning): subtract the
    local median background (banding/mottle), then threshold at the quantile
    of the CONSTRUCTION ink prior. Fixed-rate detector: decoded ink fraction
    is pinned at the prior (the 50%-median rule of 001/002 is the p=0.5 case;
    that rule breaks for 1/3- and 1/5-ink planes where the local median sits
    inside the white cluster)."""
    m = np.asarray(means, np.float64)
    resid = m - ndimage.median_filter(m, size=med_size, mode="nearest")
    thr = float(np.quantile(resid, p_ink))
    return (resid < thr).astype(np.uint8)


def _free_f32(scan: dict, channel: str | None = None) -> None:
    if channel is None:
        scan.pop("_f32", None)
    else:
        scan.get("_f32", {}).pop(channel, None)


def _pctiles(a: np.ndarray) -> dict:
    return {"mean": float(np.mean(a)), "std": float(np.std(a)),
            "p10": float(np.percentile(a, 10)),
            "p50": float(np.percentile(a, 50)),
            "p90": float(np.percentile(a, 90)), "n": int(a.size)}


# ---------------------------------------------------------------------------
# v4 decode wrappers (scanlab decode_cells; GT for templates + scoring only)
# ---------------------------------------------------------------------------

def v4_means(scan: dict, e_like: dict, gt_dots: np.ndarray, cell_dots: int,
             channel: str) -> dict:
    """scanlab.decode_cells v4 (dense poly2 warp + stepped y-profile), means
    only — the hard bits are re-derived with the fixed-rate rule outside.
    e_like needs x_dots/y_dots only (attribution: cc.decode_patch)."""
    out = scanlab.decode_cells(cc._channel_f32(scan, channel), scan["affine"],
                               e_like, gt_dots.astype(np.uint8), cell_dots,
                               soft=False, diagnostics=False)
    return out


def decode_dot_field(scan: dict, name: str, *, channel: str,
                     p_ink: float) -> tuple[dict, np.ndarray, np.ndarray]:
    """Per-dot decode of a dot-addressed K field: v4 dense warp sampled at the
    dot grid (2 scan px/dot), fixed-rate threshold at the manifest ink
    fraction, GT-aware null. Returns (record, bits, means)."""
    e = cc.entry(scan["manifest"], name)
    gt = cc.load_gt(e)
    out = v4_means(scan, e, gt, 1, channel)
    m = np.asarray(out["means"], np.float64)
    bits = fixed_rate_bits(m, p_ink)
    rec = ber_with_gt_null(bits, gt)
    gtb = gt.astype(bool)
    err = bits.astype(bool) != gtb
    rec.update({
        "patch": name, "channel": channel, "cell_dots": 1,
        "p_ink_prior": float(p_ink),
        "miss": float(err[gtb].mean()), "fa": float(err[~gtb].mean()),
        "mi_bits_hard": mi_hard_bits(gt, bits),
        "warp_windows": f"{out['warp_windows_used']}/{out['warp_windows_total']}",
        "poly_resid_rms_dots": float(out["poly_resid_rms_dots"]),
        "threshold_rule": f"local-med{MED_SIZE} residual < q(p_ink)",
    })
    return rec, bits, m


def decode_state_plane(scan: dict, name: str, p_ink: float,
                       means_cache: dict) -> dict:
    """v4 decode of one state-field plane bitmap + fixed-rate bits at the
    construction prior + GT-aware null + crosstalk splits by the union of the
    sibling planes' GT. Dot-disjoint construction => GT-ink cells never carry
    other-plane ink: the 002.1 miss@overlap knockout split is vacuous here;
    the informative split is FALSE ALARMS at other-ink cells (crosstalk)."""
    mf = scan["manifest"]
    e = cc.entry(mf, name)
    cell = int(e["params"]["cell_dots"])
    rec: dict = {"patch": name, "plane": e["planes"][0],
                 "p_ink_prior": float(p_ink)}
    try:
        out = cc.decode_patch(scan, e, soft=False, diagnostics=False)
        m = np.asarray(out["means"], np.float64)
        rec.update(method="decode_cells_v4", channel=out["channel"],
                   warp_windows=f"{out['warp_windows_used']}/"
                                f"{out['warp_windows_total']}",
                   poly_resid_rms_dots=float(out["poly_resid_rms_dots"]),
                   ber_median_rule_diag=float(out["ber"]))
        gc = out["gt_cells"]
    except Exception as exc:  # rigid fallback, recorded (cal_color pattern)
        v = cc.patch_view(scan, e)
        m = np.asarray(cc.cell_means(v, cell), np.float64)
        gc = cc.gt_cells(e)[: m.shape[0], : m.shape[1]]
        rec.update(method="rigid_patch_view", channel=v.reg_channel,
                   fallback_reason=repr(exc), lock_q=v.local_quality)
    bits = fixed_rate_bits(m, p_ink)
    rec.update(ber_with_gt_null(bits, gc))
    rec["mi_bits_hard"] = mi_hard_bits(gc, bits)
    means_cache[name] = m

    # crosstalk split by union of sibling planes' cell GT
    comp = e.get("composite_of")
    if comp:
        u = np.zeros_like(gc, dtype=bool)
        for sib in mf["patches"]:
            if sib.get("composite_of") == comp and sib["name"] != name:
                sg = cc.load_gt(sib)[::cell, ::cell].astype(bool)
                u |= sg[: gc.shape[0], : gc.shape[1]]
        gtb = gc.astype(bool)
        err = bits.astype(bool) != gtb
        rec["split_other_ink"] = {
            "fa_at_other_ink": acp._split(err, ~gtb & u),
            "fa_at_white": acp._split(err, ~gtb & ~u),
            "miss_all": acp._split(err, gtb),
            "overlap_cells": int((gtb & u).sum()),
            "note": "dot-disjoint by construction: 0 overlap cells, "
                    "knockout split vacuous; fa@other-ink = crosstalk",
        }
    return rec


def decode_d4_half(scan: dict, plane: str) -> dict:
    """D4 half (210x423 dots, non-square): v4-decode two stacked 210x210
    squares (cells 0-69 and 71-140; the 70th row is skipped to stay on the
    cell grid) and pool. Same fixed-rate rule (p = 1/3)."""
    e = cc.entry(scan["manifest"], f"D4_{plane}")
    gt = cc.load_gt(e)
    ch = cc.REG_CHANNEL_FOR_PLANE[plane]
    bits_l, gc_l, wins = [], [], []
    for y0_dots in (0, 213):
        e_like = {"x_dots": e["x_dots"], "y_dots": e["y_dots"] + y0_dots}
        g = gt[y0_dots: y0_dots + 210]
        out = v4_means(scan, e_like, g, CELL_DOTS, ch)
        m = np.asarray(out["means"], np.float64)
        bits_l.append(fixed_rate_bits(m, 1 / 3))
        gc_l.append(g[::CELL_DOTS, ::CELL_DOTS])
        wins.append(f"{out['warp_windows_used']}/{out['warp_windows_total']}")
    bits = np.concatenate(bits_l, axis=0)
    gc = np.concatenate(gc_l, axis=0)
    rec = ber_with_gt_null(bits, gc)
    rec.update({"patch": f"D4_{plane}", "plane": plane, "channel": ch,
                "p_ink_prior": 1 / 3, "method": "decode_cells_v4_2squares",
                "warp_windows": "+".join(wins),
                "mi_bits_hard": mi_hard_bits(gc, bits),
                "note": "two stacked 210x210 squares (center cell row 70 "
                        "dropped by the generator split)"})
    return rec


# ---------------------------------------------------------------------------
# screening spectra (002.1 canary-A machinery; lattice per patch, 002.2 form)
# ---------------------------------------------------------------------------

def _offgt_stats_lattice(exc_print: np.ndarray, exc_gt: np.ndarray | None,
                         fx: np.ndarray, fy: np.ndarray,
                         cell_dots: int) -> dict:
    """ao2._offgt_stats_cell with empty-mask guards: at cell_dots=1 (dot-
    addressed fields) the in-band cell-lattice bin set is EMPTY by
    construction (bins sit at 0/±1 cyc/dot, outside 0.04<r<0.9), so the
    lattice peak is reported as None instead of crashing. Math otherwise
    identical (attribution: analyze_overlap2, exp 002.2)."""
    FX, FY, r = acp._freq_grids(fx, fy)
    base = (r > 0.04) & (r < 0.9)
    lat = acp._lattice_bins(FX, FY, cell_dots)
    art = acp._artifact_bins(FX, FY)
    mask = base & ~lat & ~art
    ctrl = None
    if exc_gt is not None:
        gt_peaks = ndimage.maximum_filter(exc_gt, size=5) > 6.0
        mask = mask & ~gt_peaks
        ctrl = float(exc_gt[mask].max())
    stat = float(exc_print[mask].max())
    i, j = np.unravel_index(int(np.argmax(np.where(mask, exc_print, -np.inf))),
                            exc_print.shape)
    f_pk = (float(FX[i, j]), float(FY[i, j]))
    n_lat = int((base & lat).sum())
    return {"max_offgt_peak_db": stat, "gt_control_db": ctrl,
            "peak_freq_cyc_per_dot": list(f_pk),
            "peak_lpi": float(math.hypot(*f_pk) * cc.HW_DPI),
            "peak_angle_deg": float(math.degrees(math.atan2(f_pk[1], f_pk[0]))),
            "cell_lattice_peak_db": (float(exc_print[base & lat].max())
                                     if n_lat else None),
            "scanchain_artifact_peak_db": float(exc_print[base & art].max()),
            "n_offgt_bins": int(mask.sum())}


def screening_patch(scan: dict, name: str, cache: dict, *,
                    lattice_cell_dots: int, data_channel: str | None = None,
                    floor_bits: np.ndarray | None = None,
                    cache_key: str | None = None) -> dict:
    """acp.screening_field with (a) the lattice exclusion at the patch's own
    pitch (lattice_cell_dots=1 for dot-addressed fields = no in-band cell
    lattice), (b) optional data channel override (e.g. the r view of an S2
    K+C composite), (c) optional composite floor bits (union GT raster when
    the channel sees several planes). Gates identical to 002.1."""
    v = cc.patch_view(scan, name)
    ch = data_channel or v.reg_channel
    exc_p, fx, fy = acp._excess_db(v.crop(ch))
    key = cache_key or f"{name}|{ch}"
    if key not in cache:
        bits = floor_bits if floor_bits is not None else cc.load_gt(v.entry)
        gt_raster = np.kron((1.0 - bits).astype(np.float32) * 255.0,
                            np.ones((v.sub, v.sub), np.float32))
        cache[key] = acp._excess_db(gt_raster)[0]
    exc_g = cache[key]
    st = _offgt_stats_lattice(exc_p, exc_g, fx, fy, lattice_cell_dots)
    fams = {fam: acp.disk_excess(exc_p, fx, fy, f)
            for fam, f in acp.SCREEN_FAMILIES.items()}
    floors = {fam: acp.disk_excess(exc_g, fx, fy, f)
              for fam, f in acp.SCREEN_FAMILIES.items()}
    return {"patch": name, "channel": ch,
            "lattice_cell_dots": lattice_cell_dots,
            "locked": bool(v.local_locked), "q": v.local_quality,
            "family_excess_db": fams, "family_gt_floor_db": floors, **st}


def h1_screening(scan: dict) -> dict:
    """Per-emission screening verdicts vs the same-sheet single-plane bar
    (+ cross-sheet b bar). D1/D2/D3 share per-plane content byte-identically
    (asserted at startup) — one cached GT spectrum per plane."""
    cache: dict = {}
    print("H1 screening spectra ...", flush=True)
    # family aliasing sanity at c3 (the 002.2 lesson): all three family points
    # must be off the c3 cell lattice or disk excess there is uninterpretable.
    fam_alias = {}
    for fam, (fx_, fy_) in acp.SCREEN_FAMILIES.items():
        on = (abs(fx_ - round(fx_ * 3) / 3) < 0.012
              and abs(fy_ - round(fy_ * 3) / 3) < 0.012)
        fam_alias[fam] = {"on_c3_lattice": bool(on)}
    dets_all: dict[str, list[dict]] = {}
    for em, names in D_EMISSIONS.items():
        dets = []
        for nm in names:
            plane = nm.rsplit("_", 1)[1]
            ck = (f"CM_{plane}" if em in ("D1", "D2", "D3")
                  else f"5st_{plane}" if em in ("D5", "D6") else None)
            dets.append(screening_patch(scan, nm, cache,
                                        lattice_cell_dots=CELL_DOTS,
                                        cache_key=ck))
        dets_all[em] = dets
    base_dets = [screening_patch(scan, nm, cache, lattice_cell_dots=lat)
                 for nm, lat in BASELINE_PATCHES]
    base_verdict = acp.variant_screening_verdict(base_dets)
    baseline_fc = set(base_verdict["screened_fc"])
    bar = baseline_fc | set(CROSS_SHEET_B_BAR)
    emissions: dict[str, dict] = {}
    for em, dets in dets_all.items():
        v = acp.variant_screening_verdict(dets)
        beyond = sorted(set(v["screened_fc"]) - bar)
        emissions[em] = {"patches": dets, "verdict": v,
                         "beyond_bar": beyond,
                         "screened": bool(beyond)}
        print(f"  {em}: screened_fc={v['screened_fc']} beyond_bar={beyond}",
              flush=True)
    qz = acp.screening_quiet_zone(scan)
    print("  quiet zone off-lattice max: "
          + " ".join(f"{ch}={qz[ch]['max_offgt_peak_db']:.1f}dB"
                     for ch in ("r", "g", "b")), flush=True)
    return {"family_alias_check_c3": fam_alias,
            "same_sheet_baseline": {"patches": base_dets,
                                    "verdict": base_verdict},
            "cross_sheet_b_bar": list(CROSS_SHEET_B_BAR),
            "bar_fc": sorted(bar),
            "emissions": emissions,
            "quiet_zone_control": qz}


def h1_ber(scan: dict, means_cache: dict) -> dict:
    """Per-plane BER of every D field (fixed-rate rule at construction prior)
    grouped by scan channel; D4 halves via stacked squares."""
    print("H1 per-plane BER (v4 means + fixed-rate threshold) ...", flush=True)
    fields: dict[str, dict] = {}
    for plane in ("C", "M"):
        rec = decode_d4_half(scan, plane)
        fields[rec["patch"]] = rec
        print(f"  {rec['patch']:6s} ch={rec['channel']} ber={rec['ber']:.4f} "
              f"null={rec['ber_null']:.3f}/{rec['null_expected_from_gt']:.3f}"
              f"{'' if rec['null_ok'] else ' NULL-FAIL'}", flush=True)
    groups = [("r", [f"{em}_C" for em in ("D1", "D2", "D3", "D5", "D6")]),
              ("g", [f"{em}_M" for em in ("D1", "D2", "D3", "D5", "D6")]),
              ("b", ["D5_Y", "D6_Y"]),
              ("grey", ["D5_K", "D6_K"])]
    for ch, names in groups:
        for nm in names:
            em = nm.rsplit("_", 1)[0]
            rec = decode_state_plane(scan, nm, D_PRIOR_INK[em], means_cache)
            fields[nm] = rec
            print(f"  {nm:6s} ch={rec['channel']} ber={rec['ber']:.4f} "
                  f"null={rec['ber_null']:.3f}/"
                  f"{rec['null_expected_from_gt']:.3f}"
                  f"{'' if rec['null_ok'] else ' NULL-FAIL'} "
                  f"[{rec['method']}]", flush=True)
        _free_f32(scan, ch)
    d4_ref = {"C": fields["D4_C"]["ber"], "M": fields["D4_M"]["ber"]}
    for nm, rec in fields.items():
        if rec["plane"] in d4_ref and not nm.startswith("D4"):
            rec["delta_vs_d4"] = float(rec["ber"] - d4_ref[rec["plane"]])
    return {"fields": fields, "d4_ref_ber": d4_ref}


def h1_qda(scan: dict, wm: dict, means_cache: dict) -> dict:
    """D5-vs-D6 5-state QDA head-to-head on decode-grade per-plane-aligned
    densities (cal_color features), 3-feature (D_r,D_g,D_b) and 4-feature
    (+D_grey K-aligned); BA capacity + best uniform subsets (002.2 port)."""
    print("H1 5-state QDA D5 vs D6 ...", flush=True)
    mf = scan["manifest"]
    out: dict = {}
    for field in ("D5", "D6"):
        e0 = cc.entry(mf, f"{field}_C")
        names: list[str] = e0["params"]["state_names"]
        states = cc.load_gt_named(e0["params"]["states_gt"],
                                  e0["_base_dir"]).astype(np.int64)
        # manifest-semantics guard: plane cell GT == state membership
        for i, p in enumerate(names):
            if p == "W":
                continue
            gcp_ = cc.gt_cells(cc.entry(mf, f"{field}_{p}"))
            if gcp_ is None or not np.array_equal(gcp_,
                                                  (states == i).astype(np.uint8)):
                raise AssertionError(f"{field}_{p}: cell GT != state plane")
        feats, feat_names = [], []
        for p in "CMYK":
            e = cc.entry(mf, f"{field}_{p}")
            m = means_cache[f"{field}_{p}"]
            ch = ("grey" if p == "K" else ccol.PRIMARY_CHANNEL[p])
            ny, nx = m.shape
            xg, yg = np.meshgrid(
                e["x_dots"] + (np.arange(nx) + 0.5) * CELL_DOTS,
                e["y_dots"] + (np.arange(ny) + 0.5) * CELL_DOTS)
            w = np.maximum(cc.white_at(wm, xg, yg, ch), 1e-3)
            feats.append((-np.log10(np.maximum(m, 1.0) / w)).ravel())
            feat_names.append(f"D_{ch}({p}-aligned)")
        y = states.ravel()
        X3 = np.stack(feats[:3], axis=1)
        X4 = np.stack(feats, axis=1)
        res3 = ccol._gaussian_cv_classify(X3, y, 5)
        res4 = ccol._gaussian_cv_classify(X4, y, 5)
        null3 = ccol._classifier_null(res3["pred"], states, 5)
        null4 = ccol._classifier_null(res4["pred"], states, 5)
        ba4 = ao2.blahut_arimoto(ao2._row_normalize(res4["confusion"]))
        subsets4 = ao2.best_uniform_subsets(res4["confusion"], names)
        out[field] = {
            "n_states": 5, "state_names": names, "n_cells": int(y.size),
            "features_3d": feat_names[:3], "features_4d": feat_names,
            "accuracy_3d": res3["accuracy"], "mi_bits_3d": res3["mi_bits"],
            "null_3d": null3,
            "accuracy_4d": res4["accuracy"], "mi_bits_4d": res4["mi_bits"],
            "null_4d": null4,
            "capacity_bits_4d": ba4["capacity_bits"],
            "best_uniform_subsets_4d": subsets4,
            "confusion_4d": res4["confusion"].tolist(),
            "class_counts": res4["class_counts"].tolist(),
            "class_mean_D_4d": res4["class_means"].tolist(),
        }
        print(f"  {field}: MI3={res3['mi_bits']:.3f} MI4={res4['mi_bits']:.3f} "
              f"acc4={res4['accuracy']:.3f} cap4={ba4['capacity_bits']:.3f} "
              f"null_ok={null4['null_ok']}", flush=True)
    out["head_to_head"] = {
        "mi4_D5_minus_D6": float(out["D5"]["mi_bits_4d"]
                                 - out["D6"]["mi_bits_4d"]),
        "anchor_002_2_screened_c3": {
            "state7_mi": ANCHORS["002.2"]["state7_c3_mi"],
            "best5_subset_mi": ANCHORS["002.2"]["best5_subset_c3_mi"]},
    }
    return out


# ---------------------------------------------------------------------------
# H3 — constrained fields at the dot grid + incumbents
# ---------------------------------------------------------------------------

def _line_runs(line: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    change = np.flatnonzero(np.diff(line.astype(np.int8))) + 1
    starts = np.concatenate(([0], change))
    ends = np.concatenate((change, [line.size]))
    return line[starts], starts, ends - starts


def run_survival(bits: np.ndarray, gt: np.ndarray, max_len: int = 7) -> dict:
    """GT-run survival (a maximal GT run 'survives' iff every dot in it is
    decoded with the run's value) by (color, length), both axes pooled, plus
    decoded/GT maximal-run-length histograms (border runs included)."""
    surv: dict[int, dict[int, list[int]]] = {0: {}, 1: {}}
    hist_gt: dict[int, dict[int, int]] = {0: {}, 1: {}}
    hist_dec: dict[int, dict[int, int]] = {0: {}, 1: {}}
    for b2, g2 in ((bits, gt), (bits.T, gt.T)):
        for i in range(g2.shape[0]):
            brow = b2[i]
            vals, starts, lens = _line_runs(g2[i])
            for v, s0, ln in zip(vals.tolist(), starts.tolist(), lens.tolist()):
                key = min(int(ln), max_len)
                d = surv[v].setdefault(key, [0, 0])
                d[0] += 1
                if bool(np.all(brow[s0: s0 + ln] == v)):
                    d[1] += 1
                hist_gt[v][key] = hist_gt[v].get(key, 0) + 1
            dv, _, dl = _line_runs(brow)
            for v, ln in zip(dv.tolist(), dl.tolist()):
                key = min(int(ln), max_len)
                hist_dec[v][key] = hist_dec[v].get(key, 0) + 1
    out: dict = {"max_len_bin": max_len, "survival": {}, "gt_run_hist": {},
                 "decoded_run_hist": {}}
    for v, tag in ((1, "ink"), (0, "white")):
        out["survival"][tag] = {
            str(ln): {"n": n, "survived": k, "rate": (k / n if n else None)}
            for ln, (n, k) in sorted(surv[v].items())}
        out["gt_run_hist"][tag] = {str(k): n for k, n in sorted(hist_gt[v].items())}
        out["decoded_run_hist"][tag] = {str(k): n
                                        for k, n in sorted(hist_dec[v].items())}
    return out


def h3_run(scan: dict) -> dict:
    print("H3 constrained K fields (dot grid) + incumbents ...", flush=True)
    mf = scan["manifest"]
    fields: dict[str, dict] = {}
    for name in ("K1", "K2", "K3"):
        e = cc.entry(mf, name)
        p_ink = float(e["params"]["ink_fraction"])
        rec, bits, _m = decode_dot_field(scan, name, channel="grey",
                                         p_ink=p_ink)
        gt = cc.load_gt(e)
        rec["constraint"] = (f"i{e['params']['min_ink_run_dots']}"
                             f"w{e['params']['min_white_run_dots']}")
        rec["sampler_entropy_bits_per_dot"] = \
            e["params"]["sampler_entropy_bits_per_dot"]
        rec["ctx_model_entropy_bits_per_dot"] = \
            e["params"]["ctx_model_entropy_bits_per_dot"]
        rec["runs"] = run_survival(bits, gt)
        s_ent = float(rec["sampler_entropy_bits_per_dot"])
        proxy = s_ent * (1.0 - _h2_bits(rec["ber"]))
        rec["rate_proxy"] = {
            "formula": "sampler_entropy x (1 - H2(dotBER))",
            "bits_per_dot": proxy,
            "bits_per_mm2": proxy * DOTS_PER_MM2,
            "caveat": "errors are ISI-correlated (run-survival tables show "
                      "it) — BSC scaling is an ESTIMATE pending trellis "
                      "detection (M2)",
        }
        fields[name] = rec
        print(f"  {name} ({rec['constraint']}): dotBER={rec['ber']:.4f} "
              f"miss={rec['miss']:.3f} fa={rec['fa']:.3f} "
              f"null={rec['ber_null']:.3f}/{rec['null_expected_from_gt']:.3f} "
              f"proxy={proxy:.3f} b/dot", flush=True)
    incumbents: dict[str, dict] = {}
    for name in ("K4/encode_c2", "K4/encode_c3"):
        e = cc.entry(mf, name)
        cell = int(e["params"]["cell_dots"])
        out = cc.decode_patch(scan, e, soft=False, diagnostics=False)
        pred = out["gt_cells"] ^ out["err_map"].astype(np.uint8)
        per_cell = 1.0 - _h2_bits(out["ber"])
        incumbents[name] = {
            "cell_dots": cell, "ber": out["ber"], "n_cells": out["cells"],
            "ber_null": out["ber_null"], "null_ok": out["null_ok"],
            "mi_bits_hard_per_cell": mi_hard_bits(out["gt_cells"], pred),
            "rate_proxy": {
                "formula": "(1 - H2(cellBER)) / cell_dots^2  (pilot cells "
                           "scored as data — GT carries pilot values)",
                "bits_per_dot": per_cell / cell ** 2,
                "bits_per_mm2": per_cell / cell ** 2 * DOTS_PER_MM2},
            "method": "decode_cells_v4 native 50%-median rule "
                      "(001/002-comparable)",
        }
        print(f"  {name}: cellBER={out['ber']:.4f} null={out['ber_null']:.3f} "
              f"-> {per_cell / cell ** 2:.4f} b/dot", flush=True)
    return {"constrained_fields": fields, "incumbents": incumbents}


# ---------------------------------------------------------------------------
# H2 — white-void C subchannel
# ---------------------------------------------------------------------------

def _dot_density_maps(scan: dict, e: dict, gt: np.ndarray, wm: dict,
                      channels: tuple[str, ...]) -> dict[str, np.ndarray]:
    """Per-dot optical density maps in the given channels, each on its own v4
    dense warp locked against the SAME (K-plane) GT — K ink is dark in every
    channel, so the lock template works in r/g/b too."""
    n = gt.shape[0]
    xg, yg = np.meshgrid(e["x_dots"] + np.arange(n) + 0.5,
                         e["y_dots"] + np.arange(n) + 0.5)
    out: dict[str, np.ndarray] = {}
    for ch in channels:
        o = v4_means(scan, e, gt, 1, ch)
        m = np.asarray(o["means"], np.float64)
        w = np.maximum(cc.white_at(wm, xg, yg, ch), 1e-3)
        out[ch] = -np.log10(np.maximum(m, 1.0) / w)
    return out


def _mark_stats(s_map: np.ndarray, marks: list[list[int]],
                mark_dots: int = 2) -> np.ndarray:
    return np.array([float(s_map[y: y + mark_dots, x: x + mark_dots].mean())
                     for y, x in marks])


def _shift_coords(marks: list[list[int]], n_dots: int, dx: int = 8,
                  mark_dots: int = 2) -> list[list[int]]:
    """Deterministic shifted-coordinate null: +dx in x, folded back by 2*dx
    when it would leave the patch."""
    out = []
    for y, x in marks:
        x2 = x + dx
        if x2 > n_dots - mark_dots:
            x2 = x - dx
        out.append([y, x2])
    return out


def h2_run(scan: dict, wm: dict, pos_var_ref: dict) -> dict:
    print("H2 white-void subchannel ...", flush=True)
    mf = scan["manifest"]
    e1 = cc.entry(mf, "S1")
    e2k = cc.entry(mf, "S2_K")
    e2c = cc.entry(mf, "S2_C")
    gt1 = cc.load_gt(e1)
    gt2k = cc.load_gt(e2k)
    gt2c = cc.load_gt(e2c)
    if not np.array_equal(gt1, gt2k):
        raise AssertionError("S1 != S2_K — paired comparison invalid")
    p_ink = float(e1["params"]["ink_fraction"])
    marks: list[list[int]] = e2k["params"]["marks"]
    n = gt1.shape[0]

    # -- K dot BER, paired per dot (identical field, same sheet) -------------
    rec1, bits1, _ = decode_dot_field(scan, "S1", channel="grey", p_ink=p_ink)
    rec2, bits2, _ = decode_dot_field(scan, "S2_K", channel="grey",
                                      p_ink=p_ink)
    err1 = bits1.astype(bool) != gt1.astype(bool)
    err2 = bits2.astype(bool) != gt1.astype(bool)
    n10 = int((err1 & ~err2).sum())
    n01 = int((~err1 & err2).sum())
    # near-mark split: K ink dots with Chebyshev distance <= 2 of a mark dot
    near = np.zeros_like(err1)
    for y, x in marks:
        near[max(0, y - 2): y + 4, max(0, x - 2): x + 4] = True
    gtb = gt1.astype(bool)
    kk = {"S1": err1, "S2": err2}
    near_split = {
        tag: {"miss_near_marks": float(err[gtb & near].mean()),
              "miss_far": float(err[gtb & ~near].mean()),
              "n_ink_near": int((gtb & near).sum())}
        for tag, err in kk.items()}
    pos_var = abs(float(pos_var_ref["ber"]) - rec1["ber"])
    delta = rec2["ber"] - rec1["ber"]
    paired = {
        "ber_S1": rec1["ber"], "ber_S2": rec2["ber"],
        "delta_ber_S2_minus_S1": float(delta),
        "discordant_S1only_errors": n10, "discordant_S2only_errors": n01,
        "n_dots": int(err1.size),
        "near_mark_split": near_split,
        "miss_near_delta_S2_minus_S1": float(
            near_split["S2"]["miss_near_marks"]
            - near_split["S1"]["miss_near_marks"]),
        "miss_far_delta_S2_minus_S1": float(
            near_split["S2"]["miss_far"] - near_split["S1"]["miss_far"]),
        "position_variance_scale": {
            "value": pos_var,
            "source": "|BER(K1) - BER(S1)| — same i2w3 construction, "
                      "different page positions, same sheet"},
        "within_position_variance": bool(abs(delta) <= max(pos_var, 0.005)),
    }
    print(f"  K dot BER: S1={rec1['ber']:.4f} S2={rec2['ber']:.4f} "
          f"delta={delta:+.4f} (pos-var scale {pos_var:.4f})  "
          f"miss near marks S2={near_split['S2']['miss_near_marks']:.3f} "
          f"S1(ctrl)={near_split['S1']['miss_near_marks']:.3f}", flush=True)

    # -- b-channel blindness check -------------------------------------------
    rec1b, _, _ = decode_dot_field(scan, "S1", channel="b", p_ink=p_ink)
    rec2b, _, _ = decode_dot_field(scan, "S2_K", channel="b", p_ink=p_ink)
    blindness = {"ber_S1_grey": rec1["ber"], "ber_S1_b": rec1b["ber"],
                 "ber_S2_grey": rec2["ber"], "ber_S2_b": rec2b["ber"],
                 "note": "C is near-invisible in b; K similar in b vs grey "
                         "=> C marks do not leak into the K channel"}
    print(f"  blindness: S2 grey={rec2['ber']:.4f} b={rec2b['ber']:.4f} "
          f"(S1 b={rec1b['ber']:.4f})", flush=True)

    # -- C-mark recovery via chroma statistic --------------------------------
    print("  C-mark chroma maps (r/g/b dot densities) ...", flush=True)
    d1 = _dot_density_maps(scan, e1, gt1, wm, ("r", "g", "b"))
    d2 = _dot_density_maps(scan, e2k, gt2k, wm, ("r", "g", "b"))
    s1_map = d1["r"] - np.maximum(d1["g"], d1["b"])
    s2_map = d2["r"] - np.maximum(d2["g"], d2["b"])
    for ch in ("r", "g", "b"):
        _free_f32(scan, ch)
    stat_null = _mark_stats(s1_map, marks)          # same coords, no marks
    stat_sig = _mark_stats(s2_map, marks)
    stat_shift = _mark_stats(s2_map, _shift_coords(marks, n))
    med = float(np.median(stat_null))
    mad = float(np.median(np.abs(stat_null - med)))
    thr = med + MARK_THR_SIGMA * 1.4826 * mad
    hits = stat_sig > thr
    fp_s1 = stat_null > thr
    fp_shift = stat_shift > thr
    miss_sites = [marks[i] for i in np.flatnonzero(~hits).tolist()]
    marks_out = {
        "n_marks": len(marks), "statistic": "s = D_r - max(D_g, D_b), "
        "mean over the 2x2 mark window (v4 dot warp, white-model densities)",
        "threshold": {"rule": f"S1 same-coordinates null median + "
                              f"{MARK_THR_SIGMA:g} robust sigma",
                      "value": float(thr), "null_median": med,
                      "null_mad": mad},
        "recovery_rate": float(hits.mean()),
        "n_hits": int(hits.sum()),
        "miss_sites_patch_dots": miss_sites,
        "false_positive_rate_S1_same_coords": float(fp_s1.mean()),
        "null_hit_rate_shifted_coords_S2": float(fp_shift.mean()),
        "signal": _pctiles(stat_sig), "null_S1": _pctiles(stat_null),
        "separation_min_signal_minus_thr": float(stat_sig.min() - thr),
    }
    print(f"  C marks: {int(hits.sum())}/{len(marks)} recovered "
          f"({hits.mean():.1%}), FP@S1={fp_s1.mean():.4f}, "
          f"shifted-null={fp_shift.mean():.4f}, thr={thr:.3f} "
          f"(signal p10 {marks_out['signal']['p10']:.3f})", flush=True)

    # -- screening S2 vs S1 (does adding C trigger the contone path?) --------
    cache: dict = {}
    union2 = ((gt2k > 0) | (gt2c > 0)).astype(np.uint8)
    s_specs = {
        "S1_grey": screening_patch(scan, "S1", cache, lattice_cell_dots=1),
        "S1_r": screening_patch(scan, "S1", cache, lattice_cell_dots=1,
                                data_channel="r"),
        "S2_grey": screening_patch(scan, "S2_K", cache, lattice_cell_dots=1,
                                   floor_bits=union2, cache_key="S2u|grey"),
        "S2_r": screening_patch(scan, "S2_K", cache, lattice_cell_dots=1,
                                data_channel="r", floor_bits=union2,
                                cache_key="S2u|r"),
    }
    s_delta = {ch: {fam: float(s_specs[f"S2_{ch}"]["family_excess_db"][fam]
                               - s_specs[f"S1_{ch}"]["family_excess_db"][fam])
                    for fam in acp.SCREEN_FAMILIES}
               for ch in ("grey", "r")}

    # -- S3 colored pilots ----------------------------------------------------
    print("  S3 colored pilots ...", flush=True)
    e3k = cc.entry(mf, "S3_K")
    gt3k = cc.load_gt(e3k)
    base = cc.load_gt_named(e3k["params"]["base_cells_gt"],
                            e3k["_base_dir"]).astype(np.uint8)
    pilots: list[list[int]] = e3k["params"]["pilot_cells"]
    nc = base.shape[0]
    pm = np.zeros((nc, nc), bool)
    for ci, cj in pilots:
        pm[ci, cj] = True
    out3 = cc.decode_patch(scan, e3k, soft=False, diagnostics=False)
    bits3 = out3["gt_cells"] ^ out3["err_map"].astype(np.uint8)
    data = ~pm
    ber_data = float((bits3[data] != base[data]).mean())
    bshift = np.roll(base, SHIFT_DOTS, axis=1)
    pshift = np.roll(pm, SHIFT_DOTS, axis=1)
    msk = data & ~pshift
    null3 = float((bits3[msk] != bshift[msk]).mean())
    pr = np.zeros_like(pm)
    pr[:, 1:] = pm[:, :-1]
    pd = np.zeros_like(pm)
    pd[1:, :] = pm[:-1, :]
    margin = (pr | pd) & data
    ber_margin = float((bits3[margin] != base[margin]).mean())
    ber_clear = float((bits3[data & ~margin] != base[data & ~margin]).mean())
    d3maps = _dot_density_maps(scan, e3k, gt3k, wm, ("r", "g", "b"))
    for ch in ("r", "g", "b"):
        _free_f32(scan, ch)
    s3_map = d3maps["r"] - np.maximum(d3maps["g"], d3maps["b"])
    ncd = (gt3k.shape[0] // CELL_DOTS)
    s3_cell = s3_map[: ncd * 3, : ncd * 3].reshape(ncd, 3, ncd, 3)[
        :, 1:3, :, 1:3].mean(axis=(1, 3))
    s_p = s3_cell[pm]
    s_ink = s3_cell[(base == 1) & ~pm]
    s_wht = s3_cell[(base == 0) & ~pm]

    def _dprime(a: np.ndarray, b: np.ndarray) -> float:
        return float(abs(a.mean() - b.mean())
                     / math.sqrt((a.var() + b.var()) / 2.0 + 1e-12))

    pilot_hits = s_p > thr
    s3_out = {
        "n_pilots": len(pilots),
        "pilot_recovery_rate_at_S2_thr": float(pilot_hits.mean()),
        "n_pilot_hits": int(pilot_hits.sum()),
        "fp_rate_at_thr_k_ink_cells": float((s_ink > thr).mean()),
        "fp_rate_at_thr_white_cells": float((s_wht > thr).mean()),
        "k_cell_ber_data": ber_data,
        "k_cell_ber_null": null3,
        "k_cell_null_ok": bool(abs(null3 - 0.5) <= NULL_TOL),
        "k_cell_ber_pilot_margin_cells": ber_margin,
        "k_cell_ber_clear_cells": ber_clear,
        "n_margin_cells": int(margin.sum()),
        "anchor_same_sheet_c3": "K4/encode_c3 (see H3 incumbents)",
        "chroma_separability": {
            "statistic": "per-cell s over the [1:3,1:3] 2x2-dot window "
                         "(avoids the pilot L-margin by construction)",
            "pilot": _pctiles(s_p), "k_ink": _pctiles(s_ink),
            "white": _pctiles(s_wht),
            "dprime_pilot_vs_white": _dprime(s_p, s_wht),
            "dprime_pilot_vs_ink": _dprime(s_p, s_ink),
            "min_margin_pilot_minus_max_other":
                float(s_p.min() - max(s_ink.max(), s_wht.max())),
        },
        "decode": {"ber_median_rule_vs_dot_gt_diag": float(out3["ber"]),
                   "warp_windows": f"{out3['warp_windows_used']}/"
                                   f"{out3['warp_windows_total']}"},
    }
    print(f"  S3: pilots {int(pilot_hits.sum())}/{len(pilots)} at S2 thr, "
          f"data-cell BER={ber_data:.4f} (margin cells {ber_margin:.4f}, "
          f"clear {ber_clear:.4f}), null={null3:.3f}", flush=True)
    return {"paired_k_ber": paired,
            "k_decodes": {"S1_grey": rec1, "S2_grey": rec2,
                          "S1_b": rec1b, "S2_b": rec2b},
            "blindness_check": blindness,
            "c_marks": marks_out,
            "screening_S2_vs_S1": {"patches": s_specs,
                                   "delta_family_db_S2_minus_S1": s_delta},
            "s3_pilots": s3_out}


# ---------------------------------------------------------------------------
# H4 — motif survival library
# ---------------------------------------------------------------------------

def h4_run(scan: dict, wm: dict) -> tuple[dict, dict]:
    print("H4 motif library (12 x 132 instances) ...", flush=True)
    mf = scan["manifest"]
    motif_names = [p["name"] for p in mf["patches"]
                   if p["kind"] == "motif_patch"]
    library: dict = {
        "source_scan": {"path": scan["path"], "sha256": scan["sha256"]},
        "z_definition": "z = clip((white_model - mean)/(white_model - p1), "
                        "0, 1.5) per dot on the v4 dense warp; 1 = full ink",
        "survival_rule": f"flux_norm >= {SURVIVAL_FLUX_MIN}",
        "motifs": {},
    }
    summary: dict = {}
    for name in motif_names:
        e = cc.entry(mf, name)
        gt = cc.load_gt(e)
        prm = e["params"]
        out = v4_means(scan, e, gt, 1, "grey")
        m = np.asarray(out["means"], np.float64)
        npd = m.shape[0]
        xg, yg = np.meshgrid(e["x_dots"] + np.arange(npd) + 0.5,
                             e["y_dots"] + np.arange(npd) + 0.5)
        white = np.maximum(cc.white_at(wm, xg, yg, "grey"), 1.0)
        black = float(np.percentile(m, 1))
        z = np.clip((white - m) / np.maximum(white - black, 1e-3), 0.0, 1.5)
        is_ink = prm["motif_kind"] == "ink"
        if is_ink:
            stamp = np.array(prm["motif_shape"], np.float64)
            hh, ww = stamp.shape
            area = float(stamp.sum())
            ys, xs = np.nonzero(stamp)
            c_nom = (float(ys.mean()), float(xs.mean()))  # in-window centroid
        else:
            hh, ww = prm["hole_h_w_dots"]
            stamp = np.ones((hh, ww), np.float64)
            area = float(hh * ww)
            c_nom = ((hh - 1) / 2.0, (ww - 1) / 2.0)
        inst_rows: list[dict] = []
        ctx_null: list[float] = []      # same-shape window in the context
        bg_null: list[float] = []       # ink only: +10,+10 background chance
        for y0, x0 in prm["instances"]:
            win = z[y0: y0 + hh, x0: x0 + ww]
            resp = win if is_ink else (1.0 - win)
            flux = float(resp[stamp > 0].mean())
            # centroid over the 1-dot-padded window (weights = response)
            wpad = (z if is_ink else 1.0 - z)[y0 - 1: y0 + hh + 1,
                                              x0 - 1: x0 + ww + 1]
            tot = float(wpad.sum())
            if tot > 1e-6:
                gy, gx = np.mgrid[0: hh + 2, 0: ww + 2]
                cy = float((wpad * gy).sum() / tot) - 1.0
                cx = float((wpad * gx).sum() / tot) - 1.0
                dy, dx = cy - c_nom[0], cx - c_nom[1]
            else:
                dy = dx = float("nan")
            inst_rows.append({"y": int(y0), "x": int(x0),
                              "flux_norm": flux,
                              "dy_dots": float(dy), "dx_dots": float(dx),
                              "survived": bool(flux >= SURVIVAL_FLUX_MIN)})
            # context null: the same-shape window centered in the 4-dot band
            # directly below the feature — CLEARED WHITE for ink motifs (the
            # erased level), SOLID PAD for white holes (the filled level).
            # Centered, so it does not graze the pad/clearance edge row.
            ny0 = y0 + hh + (4 - min(hh, 4)) // 2
            if ny0 + hh <= npd:
                nwin = z[ny0: ny0 + hh, x0: x0 + ww]
                nresp = nwin if is_ink else (1.0 - nwin)
                ctx_null.append(float(nresp[stamp > 0].mean()))
            if is_ink:  # background chance level: half the lattice pitch away
                by0, bx0 = y0 + 10, x0 + 10
                if by0 + hh <= npd and bx0 + ww <= npd:
                    bwin = z[by0: by0 + hh, bx0: bx0 + ww]
                    bg_null.append(float(bwin[stamp > 0].mean()))
        flux_arr = np.array([r["flux_norm"] for r in inst_rows])
        dy_arr = np.array([r["dy_dots"] for r in inst_rows])
        dx_arr = np.array([r["dx_dots"] for r in inst_rows])
        good = np.isfinite(dy_arr)
        surv_rate = float(np.mean([r["survived"] for r in inst_rows]))
        # detection vs the context-null level (same robust rule as the H2
        # C-mark detector: null median + MARK_THR_SIGMA robust sigma)
        cn = np.array(ctx_null)
        cmed = float(np.median(cn))
        cmad = float(np.median(np.abs(cn - cmed)))
        det_thr = cmed + MARK_THR_SIGMA * 1.4826 * cmad
        det = flux_arr > det_thr
        for r_, d_ in zip(inst_rows, det.tolist()):
            r_["detected"] = bool(d_)
        entry_out = {
            "motif": prm["motif"], "kind": prm["motif_kind"],
            "shape": prm["motif_shape"], "hole_h_w_dots": prm["hole_h_w_dots"],
            "area_dots": area, "n_instances": len(inst_rows),
            "detection_rate": float(det.mean()),
            "detection_thr_flux_norm": float(det_thr),
            "survival_rate": surv_rate,
            "flux_norm": _pctiles(flux_arr),
            "centroid_dy_dots": _pctiles(dy_arr[good]),
            "centroid_dx_dots": _pctiles(dx_arr[good]),
            "context_null_flux_norm": _pctiles(cn),
            "background_null_flux_norm": (_pctiles(np.array(bg_null))
                                          if bg_null else None),
            "null_windows": "context: same-shape window centered in the "
                            "4-dot band below the feature (cleared white for "
                            "ink = erased level; solid pad for holes = "
                            "filled level); background (ink only): +10,+10 "
                            "dots = 50% c3 chance level",
            "warp_windows": f"{out['warp_windows_used']}/"
                            f"{out['warp_windows_total']}",
            "instances": inst_rows,
        }
        library["motifs"][prm["motif"]] = entry_out
        summary[prm["motif"]] = {
            k: entry_out[k] for k in ("kind", "area_dots", "detection_rate",
                                      "survival_rate")}
        summary[prm["motif"]]["flux_mean"] = entry_out["flux_norm"]["mean"]
        summary[prm["motif"]]["flux_std"] = entry_out["flux_norm"]["std"]
        summary[prm["motif"]]["dy_mean"] = entry_out["centroid_dy_dots"]["mean"]
        summary[prm["motif"]]["dx_mean"] = entry_out["centroid_dx_dots"]["mean"]
        summary[prm["motif"]]["ctx_null_mean"] = \
            entry_out["context_null_flux_norm"]["mean"]
        print(f"  {prm['motif']:16s} det={det.mean():.3f} surv={surv_rate:.3f} "
              f"flux={flux_arr.mean():.3f}+-{flux_arr.std():.3f} "
              f"dyx=({np.nanmean(dy_arr):+.2f},{np.nanmean(dx_arr):+.2f}) "
              f"ctx-null={cmed:.3f}", flush=True)
    return summary, library


# ---------------------------------------------------------------------------
# verdicts, null rollup, draft
# ---------------------------------------------------------------------------

def h1_verdicts(scr: dict, ber: dict, qda: dict) -> dict:
    """Per-emission H1 decision: clean-path equivalent = screen-free beyond
    the bar AND every C/M plane within +0.02 BER of its D4 half (002.1 rule).
    D3/D6 are the screened positive controls — they must FAIL or the
    discriminator is broken."""
    emissions: dict[str, dict] = {}
    for em in D_EMISSIONS:
        e_scr = scr["emissions"][em]
        recs = [r for nm, r in ber["fields"].items()
                if nm.startswith(em + "_") and "delta_vs_d4" in r]
        deltas = {r["patch"]: r["delta_vs_d4"] for r in recs}
        ber_ok = all(d <= BER_GATE_ABS for d in deltas.values()) if deltas \
            else None
        emissions[em] = {
            "screened_beyond_bar": e_scr["beyond_bar"],
            "screen_free": not e_scr["screened"],
            "ber_delta_vs_d4": deltas,
            "ber_within_gate": ber_ok,
            "verdict": ("clean" if (not e_scr["screened"]
                                    and (ber_ok is not False)) else "screened"
                        if e_scr["screened"] else "clean-spectra_ber-off"),
        }
    pos_ctrl = emissions["D3"]["screened_beyond_bar"] or \
        emissions["D6"]["screened_beyond_bar"]
    h1 = {
        "emissions": emissions,
        "positive_control_D3_or_D6_screened": bool(pos_ctrl),
        "headline": None,
    }
    d1c, d2c = (not scr["emissions"]["D1"]["screened"],
                not scr["emissions"]["D2"]["screened"])
    d5c = not scr["emissions"]["D5"]["screened"]
    if not pos_ctrl:
        h1["headline"] = ("POSITIVE CONTROL FAILED: cmyk-image controls "
                          "measured screen-free — do not conclude anything")
    else:
        trig = ("dot" if (d1c and d2c) else
                "region" if not (d1c or d2c) else "mixed")
        h1["headline"] = (
            f"screening trigger = {trig.upper()}-overlap: D1 "
            f"{'clean' if d1c else 'screened'}, D2 (13,225 objects) "
            f"{'clean' if d2c else 'screened'}, D5 (4-plane) "
            f"{'clean' if d5c else 'screened'}; D3/D6 cmyk controls screened "
            f"(positive control good)")
    mi5 = qda["D5"]["mi_bits_4d"]
    h1["leaderboard"] = {
        "d5_mi4": mi5, "d6_mi4": qda["D6"]["mi_bits_4d"],
        "screened_002_2_c3_refs": qda["head_to_head"][
            "anchor_002_2_screened_c3"],
        "d5_clean_and_beats_screened_c3": bool(
            d5c and mi5 > ANCHORS["002.2"]["state7_c3_mi"]),
    }
    return h1


def collect_nulls(rep: dict) -> dict:
    entries: list[tuple[str, bool]] = []

    def walk(d: dict, path: str) -> None:
        if "null_ok" in d and isinstance(d["null_ok"], (bool, np.bool_)):
            entries.append((path, bool(d["null_ok"])))
        for k, v in d.items():
            if isinstance(v, dict):
                walk(v, f"{path}/{k}")
    for key in ("h1", "h2", "h3"):
        walk(rep[key], key)
    failures = [p for p, ok in entries if not ok]
    return {"n_total": len(entries), "failures": failures}


def _fc_short(fcs: list[str]) -> str:
    """'165lpi_pm14deg|g' -> '165·g' (markdown-table-safe, 002.2 precedent)."""
    return ", ".join(f"{f.split('lpi', 1)[0]}·{f.split('|', 1)[1]}"
                     for f in fcs) or "—"


def write_draft(rep: dict, path: Path) -> None:
    scr, ber, qda = (rep["h1"]["screening"], rep["h1"]["ber"],
                     rep["h1"]["qda"])
    ver = rep["h1"]["verdicts"]
    h2, h3, h4 = rep["h2"], rep["h3"], rep["h4_summary"]
    reg = rep["registration"]
    L: list[str] = []
    a = L.append
    a("<!-- draft completion of the 003.0 RESULTS entry; paste below the run "
      "header table in experiments/003-modulation-probes.md -->")
    a("")
    a(f"| scan | `scans/test-scan-modprobe.png` RGBA 1200 dpi, 0°, sha256 "
      f"`{rep['scan']['sha256']}` |")
    a(f"| analyzer | `analyze_modprobe.py` → `build/modprobe_report.json` + "
      f"`build/motif_library.json` ({rep['elapsed_s']:.0f} s); spectra gates "
      "imported unchanged from 002.1/002.2 (`analyze_composite_probe` / "
      "`analyze_overlap2`), QDA from `cal_color` |")
    nc = rep["null_controls"]
    a(f"| discipline | one threshold rule everywhere (local-median residual + "
      f"quantile at the construction ink prior — the 001/002 50%-median rule "
      f"is its p=0.5 case); {nc['n_total']} null controls judged against "
      f"GT-derived expected levels "
      f"({'ALL PASS' if not nc['failures'] else 'FAILURES: ' + ', '.join(nc['failures'])}); "
      "no per-patch tuning |")
    a("")
    a(f"Registration: {reg['n_landmarks_used']}/{reg['n_landmarks_total']} "
      f"landmarks (4 chiral corners + 58 plus), residual RMS "
      f"{reg['residual_rms_dots']:.2f} dots (max {reg['residual_max_dots']:.2f}), "
      f"rot {reg['rotation_deg']:.3f}°, px/dot {reg['px_per_dot_x']:.5f}/"
      f"{reg['px_per_dot_y']:.5f} (y +{(reg['px_per_dot_y'] / 2 - 1) * 100:.2f}% "
      "— hygro envelope); ruler_check reports the expected KeyError (no "
      "rulers on this page).")
    a("")
    a("#### H1 — screening trigger on dot-disjoint multi-plane emission "
      "(THE headline)")
    a("")
    a(f"**{rep['h1']['verdicts']['headline']}**")
    a("")
    a("Screen-family disk excess (dB; hit bar = max(12, GT floor+6), strong "
      "bar 18 — 002.1 gates verbatim). Same-sheet clean bar (D4 + K4 + S1): "
      f"{_fc_short(scr['same_sheet_baseline']['verdict']['screened_fc']) if scr['same_sheet_baseline']['verdict']['screened_fc'] else 'none (clean)'}"
      f"; cross-sheet b bar (002.1 Y-plane texture): "
      f"{_fc_short(list(scr['cross_sheet_b_bar']))}.")
    a("")
    a("| emission | patch | ch | 165 lpi | 212 lpi | 224 lpi | beyond bar |")
    a("|---|---|---|---|---|---|---|")
    for em in D_EMISSIONS:
        for d in scr["emissions"][em]["patches"]:
            f_ = d["family_excess_db"]
            fl = d["family_gt_floor_db"]
            a(f"| {em} | {d['patch']} | {d['channel']} | "
              f"{f_['165lpi_pm14deg']:.1f} ({fl['165lpi_pm14deg']:.1f}) | "
              f"{f_['212lpi_45deg']:.1f} ({fl['212lpi_45deg']:.1f}) | "
              f"{f_['224lpi_pm27deg']:.1f} ({fl['224lpi_pm27deg']:.1f}) | "
              f"{_fc_short(scr['emissions'][em]['beyond_bar'])} |")
    a("")
    a("(family excess with each patch's own GT-spectrum floor in parens; all "
      "three family points verified off the c3 cell lattice, so no 002.2-"
      "style aliasing at c3.)")
    a("")
    a("Per-plane BER, fixed-rate threshold at the construction prior (1/3 for "
      "CM fields, 1/5 for 5-state), GT-aware nulls:")
    a("")
    a("| patch | ch | BER | Δ vs D4 half | miss/fa split note | null (exp) |")
    a("|---|---|---|---|---|---|")
    for nm, r in ber["fields"].items():
        d4d = (f"{r['delta_vs_d4']:+.4f}" if "delta_vs_d4" in r else "—")
        s = r.get("split_other_ink")
        xs = (f"fa@other-ink {s['fa_at_other_ink']['err']:.3f} vs white "
              f"{s['fa_at_white']['err']:.3f}" if s else "single-plane ref")
        a(f"| {nm} | {r['channel']} | {r['ber']:.4f} | {d4d} | {xs} | "
          f"{r['ber_null']:.3f} ({r['null_expected_from_gt']:.3f}) |")
    a("")
    a("5-state QDA head-to-head (W,C,M,Y,K at c3; features = per-plane-"
      "aligned densities D_r/D_g/D_b [+ D_grey K-aligned]):")
    a("")
    a("| field | acc (4-feat) | MI 3-feat | MI 4-feat | BA cap | best-4 "
      "subset | null ok |")
    a("|---|---|---|---|---|---|---|")
    for f_ in ("D5", "D6"):
        r = qda[f_]
        b4 = r["best_uniform_subsets_4d"]["4"]
        a(f"| {f_} | {r['accuracy_4d']:.3f} | {r['mi_bits_3d']:.3f} | "
          f"{r['mi_bits_4d']:.3f} | {r['capacity_bits_4d']:.3f} | "
          f"{b4['mi_bits']:.3f} {{{','.join(b4['states'])}}} | "
          f"{r['null_4d']['null_ok']} |")
    lb = rep["h1"]["verdicts"]["leaderboard"]
    a("")
    a(f"Leaderboard: D5 (dot-disjoint masks) MI4 {lb['d5_mi4']:.3f} vs D6 "
      f"(cmyk) {lb['d6_mi4']:.3f} vs 002.2 screened c3 printed-7-state "
      f"{ANCHORS['002.2']['state7_c3_mi']:.3f} / best-5-subset "
      f"{ANCHORS['002.2']['best5_subset_c3_mi']:.3f} → D5 clean AND beats "
      f"screened c3: **{lb['d5_clean_and_beats_screened_c3']}**.")
    a("")
    a("#### H2 — white-void C subchannel")
    a("")
    pk = h2["paired_k_ber"]
    a(f"- K dot-BER S1 {pk['ber_S1']:.4f} vs S2 {pk['ber_S2']:.4f} "
      f"(Δ {pk['delta_ber_S2_minus_S1']:+.4f}; position-variance scale "
      f"{pk['position_variance_scale']['value']:.4f} → within variance: "
      f"{pk['within_position_variance']}); discordant dots S1-only "
      f"{pk['discordant_S1only_errors']} vs S2-only "
      f"{pk['discordant_S2only_errors']} of {pk['n_dots']}.")
    ns = pk["near_mark_split"]
    a(f"- K miss near marks (Chebyshev ≤2): S2 "
      f"{ns['S2']['miss_near_marks']:.4f} vs far {ns['S2']['miss_far']:.4f}; "
      f"S1 control at the SAME sites {ns['S1']['miss_near_marks']:.4f} vs "
      f"{ns['S1']['miss_far']:.4f}. Mechanism reading: the near-mark delta is "
      f"{pk['miss_near_delta_S2_minus_S1']:+.4f} (S2 not worse at marks) "
      f"while the FAR-field delta is {pk['miss_far_delta_S2_minus_S1']:+.4f} "
      "and the b-channel (C-blind) shows the same global shift — so NO local "
      "development coupling at marks; the global Δ is a position/field "
      "effect, not a C effect (single replicate — needs a repeat to close). "
      "Note void-adjacent K ink misses at ~25–27% in BOTH fields vs ~15% "
      "far-field: enforced white voids cost their K neighbors dearly "
      "(001 anisotropy), C presence irrelevant.")
    cm = h2["c_marks"]
    a(f"- C-mark recovery {cm['n_hits']}/{cm['n_marks']} "
      f"({cm['recovery_rate']:.1%}) at s = D_r − max(D_g,D_b) > {cm['threshold']['value']:.3f} "
      f"(S1-null median + {MARK_THR_SIGMA:g}σ); FP on S1 same-coords "
      f"{cm['false_positive_rate_S1_same_coords']:.4f}, shifted-coords null "
      f"{cm['null_hit_rate_shifted_coords_S2']:.4f}; min signal − thr = "
      f"{cm['separation_min_signal_minus_thr']:+.3f}.")
    bl = h2["blindness_check"]
    a(f"- K-channel blindness: S2 K dot-BER grey {bl['ber_S2_grey']:.4f} vs "
      f"b-channel {bl['ber_S2_b']:.4f} (S1 b control {bl['ber_S1_b']:.4f}).")
    sd = h2["screening_S2_vs_S1"]["delta_family_db_S2_minus_S1"]
    a("- Screening S2 − S1 family delta (dB): grey "
      + " ".join(f"{f_[:3]} {v:+.1f}" for f_, v in sd["grey"].items())
      + "; r " + " ".join(f"{f_[:3]} {v:+.1f}" for f_, v in sd["r"].items())
      + ".")
    s3 = h2["s3_pilots"]
    cs = s3["chroma_separability"]
    a(f"- S3 pilots: {s3['n_pilot_hits']}/{s3['n_pilots']} recovered at the "
      f"S2 threshold; K data-cell BER {s3['k_cell_ber_data']:.4f} "
      f"(pilot-margin cells {s3['k_cell_ber_pilot_margin_cells']:.4f}, clear "
      f"{s3['k_cell_ber_clear_cells']:.4f}) vs same-sheet K4/encode_c3 "
      f"{rep['h3']['incumbents']['K4/encode_c3']['ber']:.4f}; chroma d' "
      f"pilot-vs-white {cs['dprime_pilot_vs_white']:.1f}, pilot-vs-ink "
      f"{cs['dprime_pilot_vs_ink']:.1f}, min margin "
      f"{cs['min_margin_pilot_minus_max_other']:+.3f} (negative: the "
      f"{s3['n_pilots']}-pilot minimum sits below the max of ~24k data "
      f"cells; blind per-cell FP at the S2 threshold: K-ink cells "
      f"{s3['fp_rate_at_thr_k_ink_cells']:.3f}, white "
      f"{s3['fp_rate_at_thr_white_cells']:.3f} — pilot detection must stay "
      "site-gated, not free-running).")
    a("")
    a("#### H3 — 2-D RLL constrained K fields at the dot grid")
    a("")
    a("| field | constraint | sampler b/dot | dot BER | miss / fa | MI hard "
      "b/dot | rate proxy b/dot | b/mm² | null (exp) |")
    a("|---|---|---|---|---|---|---|---|---|")
    for nm in ("K1", "K2", "K3"):
        r = h3["constrained_fields"][nm]
        rp = r["rate_proxy"]
        a(f"| {nm} | {r['constraint']} | "
          f"{r['sampler_entropy_bits_per_dot']:.4f} | {r['ber']:.4f} | "
          f"{r['miss']:.3f} / {r['fa']:.3f} | {r['mi_bits_hard']:.3f} | "
          f"{rp['bits_per_dot']:.3f} | {rp['bits_per_mm2']:.0f} | "
          f"{r['ber_null']:.3f} ({r['null_expected_from_gt']:.3f}) |")
    for nm in ("K4/encode_c2", "K4/encode_c3"):
        r = h3["incumbents"][nm]
        rp = r["rate_proxy"]
        a(f"| {nm} | c{r['cell_dots']} solid cells | 1/cell | {r['ber']:.4f} "
          f"(cell) | — | {r['mi_bits_hard_per_cell']:.3f}/cell | "
          f"{rp['bits_per_dot']:.3f} | {rp['bits_per_mm2']:.0f} | "
          f"{r['ber_null']:.3f} (0.500) |")
    a("")
    a("Run survival (fraction of GT maximal runs decoded fully intact, both "
      "axes; the '2-runs and 3-runs die where?' table):")
    a("")
    a("| field | ink L=2 | ink 3 | ink 4 | ink ≥7 | white 2 | white 3 | "
      "white 4 | white ≥7 |")
    a("|---|---|---|---|---|---|---|---|---|")
    for nm in ("K1", "K2", "K3"):
        sv = h3["constrained_fields"][nm]["runs"]["survival"]

        def g(tag: str, ln: str) -> str:
            d = sv[tag].get(ln)
            return f"{d['rate']:.2f}" if d and d["rate"] is not None else "—"
        a(f"| {nm} | {g('ink', '2')} | {g('ink', '3')} | {g('ink', '4')} | "
          f"{g('ink', '7')} | {g('white', '2')} | {g('white', '3')} | "
          f"{g('white', '4')} | {g('white', '7')} |")
    a("")
    a("Rate-proxy caveat (honest): dot errors are ISI-correlated (run "
      "survival above), so sampler_entropy × (1 − H2(BER)) is an ESTIMATE "
      "pending trellis/context detection (M2), not a measured capacity.")
    a("")
    a("#### H4 — motif survival library (→ `build/motif_library.json`)")
    a("")
    a("detect = flux above the context-null (erased/filled level in the "
      "4-dot band below the feature) + 4 robust σ — same rule as the H2 "
      "C-mark detector; survive = flux_norm ≥ 0.5 (development strength).")
    a("")
    a("| motif | kind | area | detect | survive | flux mean±σ | centroid "
      "(dy,dx) | ctx-null flux |")
    a("|---|---|---|---|---|---|---|---|")
    for nm, s in h4.items():
        a(f"| {nm} | {s['kind']} | {s['area_dots']:.0f} | "
          f"{s['detection_rate']:.3f} | {s['survival_rate']:.3f} | "
          f"{s['flux_mean']:.3f}±{s['flux_std']:.3f} | "
          f"({s['dy_mean']:+.2f},{s['dx_mean']:+.2f}) | "
          f"{s['ctx_null_mean']:.3f} |")
    a("")
    a("#### Caveats (facts, not editorializing)")
    a("")
    a("- Fixed-rate detector: decoded ink fraction is pinned at the "
      "construction prior per patch — BERs are rank-threshold BERs; a "
      "blind-threshold decoder would need the prior from elsewhere (it has "
      "it: the constraint/alphabet is a design constant).")
    a("- Null controls for structured/asymmetric fields are judged against "
      "the GT-derived expected level (RLL autocorrelation at shift 8, "
      "2p(1−p) for 1/3- and 1/5-ink planes), not the flat 0.50 of 001/002.")
    a("- No same-sheet single-plane Y or K-in-color-field screening "
      "reference: the b-channel bar is CROSS-SHEET (002.1 P4 {165|b, "
      "224|b}); D5/D6 Y-plane spectra are judged against it.")
    a("- QDA MI carries the cal_color interleaved-fold optimism bias; "
      "D5-vs-D6 and vs-002.2 comparisons share the bias (like-for-like).")
    a("- H3 rate proxies assume BSC error scaling; ISI correlation is "
      "measured and reported but not modeled. Trellis detection (M2) is the "
      "follow-up.")
    a("- Single sheet, single scan, one page position per config; same-sheet "
      "position variance visible as K1-vs-S1 BER spread "
      f"({rep['h2']['paired_k_ber']['position_variance_scale']['value']:.4f}).")
    a("- S3 pilot-void margins eat the left column/top row of "
      "right/below-neighbor cells; their BER is reported split "
      "(margin vs clear) rather than corrected.")
    qz = rep["h1"]["screening"]["quiet_zone_control"]
    a("- Quiet-zone off-lattice max reads "
      + "/".join(f"{qz[ch]['max_offgt_peak_db']:.0f}" for ch in ("r", "g", "b"))
      + " dB (r/g/b) from banding-type lines at ~(0, ±0.13) and (±0.75, 0) "
        "cyc/dot — NOT at screen-family points (family disks in the quiet "
        "zone read 8–10 dB = chance), so family verdicts are unaffected.")
    a("- The S2 shifted-coordinate mark null trips at "
      f"{rep['h2']['c_marks']['null_hit_rate_shifted_coords_S2']:.1%}: "
      "shifted windows can land on OTHER marks (557 marks pepper the field) "
      "— the clean no-C null is FP@S1 same-coords "
      f"({rep['h2']['c_marks']['false_positive_rate_S1_same_coords']:.4f}).")
    a("- H4 context nulls sit 1–2 dots from the feature and the pad/clear "
      "edge (the context band is only 4 dots) — they carry residual PSF "
      "spill; small-motif flux distributions are UNIMODAL (see library "
      "percentiles): weak development, not stochastic death, so 'survive' "
      "is a threshold statement, 'detect' the presence statement.")
    path.write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def analyze(scan_path: Path) -> dict:
    t0 = time.time()
    mf_sha = hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()
    manifest = cc.load_manifest(MANIFEST_PATH)

    # construction invariants the analysis relies on (asserted, not assumed)
    gt = {n: cc.load_gt(cc.entry(manifest, n))
          for n in ("D1_C", "D1_M", "D2_C", "D2_M", "D3_C", "D3_M",
                    "S1", "S2_K")}
    for p in ("C", "M"):
        for v in ("D2", "D3"):
            if not np.array_equal(gt[f"D1_{p}"], gt[f"{v}_{p}"]):
                raise AssertionError(f"D1_{p} != {v}_{p} (GT identity broken)")
    if not np.array_equal(gt["S1"], gt["S2_K"]):
        raise AssertionError("S1 != S2_K (paired H2 comparison invalid)")
    st = cc.load_gt_named("modprobe_gt/D_cm_states.npy",
                          manifest["_base_dir"]).astype(int)
    d4c = cc.load_gt(cc.entry(manifest, "D4_C"))
    d4m = cc.load_gt(cc.entry(manifest, "D4_M"))
    if not (np.array_equal(d4c[::3, ::3], (st[:, :70] == 1).astype(np.uint8))
            and np.array_equal(d4m[::3, ::3],
                               (st[:, 71:] == 2).astype(np.uint8))):
        raise AssertionError("D4 halves != state-field columns")
    del gt

    print(f"loading + registering {scan_path}", flush=True)
    scan = cc.load_scan(scan_path)
    sha_ok = scan["sha256"] == EXPECTED_SCAN_SHA256
    if not sha_ok:
        print(f"!! scan sha256 {scan['sha256']} != expected", flush=True)
    reg = cc.register(scan, manifest)
    rms = reg["residual_rms_dots"]
    print(f"  {scan['kind']}, {reg['n_landmarks_used']}/"
          f"{reg['n_landmarks_total']} landmarks, residual RMS {rms:.3f} dots "
          f"(max {reg['residual_max_dots']:.3f}), rot {reg['rotation_deg']:.3f} "
          f"deg, px/dot {reg['px_per_dot_x']:.5f}/{reg['px_per_dot_y']:.5f}",
          flush=True)
    if rms is None or rms >= acp.REG_RMS_GATE_DOTS:
        raise cc.RegistrationError(f"residual RMS {rms} >= "
                                   f"{acp.REG_RMS_GATE_DOTS}")
    print("white model ...", flush=True)
    wm = cc.white_model(scan)

    # ---- H1 -----------------------------------------------------------------
    scr = h1_screening(scan)
    means_cache: dict = {}
    ber = h1_ber(scan, means_cache)
    qda = h1_qda(scan, wm, means_cache)
    means_cache.clear()
    _free_f32(scan)

    # ---- H3 (before H2: K1 feeds the position-variance scale) ---------------
    h3 = h3_run(scan)

    # ---- H2 -----------------------------------------------------------------
    h2 = h2_run(scan, wm, h3["constrained_fields"]["K1"])
    _free_f32(scan)

    # ---- H4 -----------------------------------------------------------------
    h4_summary, motif_library = h4_run(scan, wm)
    cc.save_report(motif_library, OUT_MOTIF)

    rep: dict = {
        "run": "003.0",
        "analyzer": "analyze_modprobe.py",
        "scan": {"path": str(scan_path), "sha256": scan["sha256"],
                 "sha256_expected": EXPECTED_SCAN_SHA256,
                 "sha256_ok": bool(sha_ok), "kind": scan["kind"],
                 "shape_px": list(scan["grey"].shape)},
        "manifest": {"path": str(MANIFEST_PATH), "sha256": mf_sha,
                     "sha256_ok": bool(mf_sha == EXPECTED_MANIFEST_SHA256),
                     "jobid": manifest["jobid"], "seed": manifest["seed"],
                     "ps_sha256": manifest["ps_sha256"]},
        "registration": reg,
        "gates": {
            "registration_rms_dots_max": acp.REG_RMS_GATE_DOTS,
            "screen_strong_db": acp.SCREEN_STRONG_DB,
            "screen_coherent_db": acp.SCREEN_COHERENT_DB,
            "disk_tol_cpd": acp.DISK_TOL_CPD,
            "ber_gate_abs": BER_GATE_ABS,
            "null_tol": NULL_TOL,
            "threshold_rule": f"local-median({MED_SIZE}) residual < "
                              "quantile(construction ink prior)",
            "mark_thr_rule": f"S1-null median + {MARK_THR_SIGMA:g} robust "
                             "sigma (one global threshold)",
            "survival_flux_min": SURVIVAL_FLUX_MIN,
            "provenance": "spectra/BER gates identical to 002.1/002.2 "
                          "(imported constants)"},
        "anchors": ANCHORS,
        "h1": {"screening": scr, "ber": ber, "qda": qda},
        "h2": h2,
        "h3": h3,
        "h4_summary": h4_summary,
        "motif_library_file": str(OUT_MOTIF),
    }
    rep["h1"]["verdicts"] = h1_verdicts(scr, ber, qda)
    rep["null_controls"] = collect_nulls(rep)
    rep["elapsed_s"] = round(time.time() - t0, 1)
    cc.save_report(rep, OUT_REPORT)
    write_draft(rep, OUT_DRAFT)

    # ---- human summary -------------------------------------------------------
    print("\n== H1 VERDICT (screening trigger) ==")
    print(rep["h1"]["verdicts"]["headline"])
    for em, v in rep["h1"]["verdicts"]["emissions"].items():
        dd = v["ber_delta_vs_d4"]
        dmax = (f" maxΔBER={max(dd.values()):+.4f}" if dd else "")
        print(f"  {em}: {v['verdict']:10s} beyond_bar="
              f"{v['screened_beyond_bar'] or 'none'}{dmax}")
    lb = rep["h1"]["verdicts"]["leaderboard"]
    print(f"  5-state c3: D5 MI4={lb['d5_mi4']:.3f} vs D6 {lb['d6_mi4']:.3f} "
          f"vs 002.2 screened 7st {ANCHORS['002.2']['state7_c3_mi']:.3f} -> "
          f"leaderboard change: {lb['d5_clean_and_beats_screened_c3']}")
    print("\n== H2 ==")
    pk = rep["h2"]["paired_k_ber"]
    cm = rep["h2"]["c_marks"]
    s3 = rep["h2"]["s3_pilots"]
    print(f"  K BER S1={pk['ber_S1']:.4f} S2={pk['ber_S2']:.4f} "
          f"delta={pk['delta_ber_S2_minus_S1']:+.4f} "
          f"(within pos-var: {pk['within_position_variance']})")
    print(f"  C marks {cm['n_hits']}/{cm['n_marks']} ({cm['recovery_rate']:.1%}), "
          f"FP@S1 {cm['false_positive_rate_S1_same_coords']:.4f}, shifted null "
          f"{cm['null_hit_rate_shifted_coords_S2']:.4f}")
    print(f"  S3 pilots {s3['n_pilot_hits']}/{s3['n_pilots']}, K data BER "
          f"{s3['k_cell_ber_data']:.4f}")
    print("\n== H3 (b/dot: proxy | b/mm2) ==")
    for nm in ("K1", "K2", "K3"):
        r = rep["h3"]["constrained_fields"][nm]
        print(f"  {nm} {r['constraint']}: BER={r['ber']:.4f} proxy="
              f"{r['rate_proxy']['bits_per_dot']:.3f} | "
              f"{r['rate_proxy']['bits_per_mm2']:.0f}")
    for nm, r in rep["h3"]["incumbents"].items():
        print(f"  {nm}: cellBER={r['ber']:.4f} -> "
              f"{r['rate_proxy']['bits_per_dot']:.3f} | "
              f"{r['rate_proxy']['bits_per_mm2']:.0f}")
    print("\n== H4 (detect | survive | flux | ctx-null) ==")
    for nm, s in rep["h4_summary"].items():
        print(f"  {nm:16s} {s['detection_rate']:.3f} | "
              f"{s['survival_rate']:.3f} | {s['flux_mean']:.3f} | "
              f"{s['ctx_null_mean']:.3f}")
    nc = rep["null_controls"]
    print(f"\nnull controls: {nc['n_total']} total, failures: "
          f"{nc['failures'] or 'none'}")
    print(f"report -> {OUT_REPORT}\nmotifs -> {OUT_MOTIF}\n"
          f"draft  -> {OUT_DRAFT}  ({rep['elapsed_s']:.0f} s)")
    return rep


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="003.0 modprobe analyzer")
    ap.add_argument("scan", nargs="?", default=str(DEFAULT_SCAN))
    args = ap.parse_args()
    analyze(Path(args.scan))

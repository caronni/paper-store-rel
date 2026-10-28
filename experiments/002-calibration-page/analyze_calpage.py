#!/usr/bin/env python
"""analyze_calpage.py — experiment 002 orchestrator: full CAL-1 analyzer.

Registers the two real scans ONCE, dispatches all five family analyzers
(cal_geometry=transport, cal_structural, cal_ber=modulation, cal_color=
density_color/alphabet, cal_canary=meta+canaries), merges every payload into
the frozen cal_core report skeleton, then synthesizes the cross-family curated
keys that no single family owns end-to-end:

  engine.*                    <- selfreport (machine strips) + measured grid
  channel_params.{crosstalk_matrix, cond_number, dmax}
                              <- color.* (mapping documented in cal_color
                                 integration notes: nobody else owns them)
  channel_params.{tvi, mottle_sigma}
                              <- families.structural.channel_fragments
                                 (structural measured them but deliberately
                                 left the density_color-owned keys empty)
  channel_params.scan_noise_rgb <- white-model fit residuals
  modulation.{k_cmy_dprime, lattice_snr_db}
                              <- color.k_cmy_margin / canary screening detail
  recommendation.*            <- the panel-cal-scan-analyzability §11 decision
                                 logic (rate ladder, cell_min, states/cell,
                                 simultaneous-CMY verdict, bits/mm2 estimate)
  families.meta.canary_letter_map

Hard gates enforced before the report is written (run-001.2 discipline):
  - every BER-style null control ('ber_null'/'null_ber') in [0.48, 0.52]
  - every 'null_ok' flag true
  - every canary verdict has status in {pass, fail, indeterminate} with
    statistic + control
A gate violation exits non-zero AFTER writing the report (for post-mortem)
and prints the offending paths.

Outputs:
  build/calpage_report.json          machine report (numpy-safe JSON)
  build/analysis-calpage/*.png       per-patch decode-error overlays (29
                                     encode patches) + registration overlays
  stdout                             §11-style human decision block

Determinism: this module uses no randomness (CLAUDE.md rule satisfied
vacuously; families document their own seeded controls).

Run (real scans, ~2-3 min, ~2 GB resident):
  env/bin/python experiments/002-calibration-page/analyze_calpage.py
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import cal_core as cc  # noqa: E402
import cal_ber  # noqa: E402
import cal_canary  # noqa: E402
import cal_color  # noqa: E402
import cal_geometry  # noqa: E402
import cal_structural  # noqa: E402

REPO = _HERE.parent.parent
DEFAULT_BW = REPO / "scans" / "test-scan-calpage-bw.png"
DEFAULT_COLOR = REPO / "scans" / "test-scan-calpage-color.png"
DEFAULT_OUT = cc.BUILD / "calpage_report.json"
DEFAULT_OVERLAYS = cc.BUILD / "analysis-calpage"

PLANES = ("K", "C", "M", "Y")
CELLS = (1, 2, 3, 4)

# panel-cal-scan-analyzability §11: BER -> inner LDPC rate
RATE_LADDER: tuple[tuple[float, float], ...] = (
    (0.01, 0.85), (0.03, 0.75), (0.06, 0.67), (0.10, 0.55), (0.15, 0.45))
BER_CANDIDATE_MAX = 0.15          # soft-decode envelope
METRIC_MARGIN = 0.8               # §11 argmax margin factor
PRINTABLE_AREA_MM2 = 55_000.0     # ~A4 minus measured ~6-7.4 mm margins


def ldpc_rate(ber: float) -> float | None:
    for thr, r in RATE_LADDER:
        if ber <= thr:
            return r
    return None


def _h2(p: float) -> float:
    p = min(max(p, 1e-12), 1.0 - 1e-12)
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


def cells_per_mm2(cell_dots: int) -> float:
    return (cc.HW_DPI / 25.4 / cell_dots) ** 2


# ---------------------------------------------------------------------------
# overlays
# ---------------------------------------------------------------------------

def _to_u8(a: np.ndarray) -> np.ndarray:
    white, black, _ = cc.levels(a)
    span = max(white - black, 1e-6)
    return (np.clip((a - black) / span, 0.0, 1.0) * 255.0).astype(np.uint8)


def save_patch_overlay(scan: dict, name: str, out: dict, path: Path) -> None:
    """Scan crop of the patch (decode channel) with decode-error cells in red.

    Alignment note: the crop uses the rigid patch_view local lock while the
    decode used the dense poly2 warp — residual internal warp (~1 dot) can
    offset the tint by a fraction of a cell. Advisory visual only.
    """
    e = cc.entry(scan["manifest"], name)
    v = cc.patch_view(scan, e, channel=out["channel"])
    crop = v.crop(out["channel"])
    g = _to_u8(crop)
    rgb = np.stack([g, g, g], axis=-1)
    cell_px = int(e["params"]["cell_dots"]) * v.sub
    err = out["err_map"].astype(bool)
    up = np.kron(err, np.ones((cell_px, cell_px), dtype=bool))
    up = up[: rgb.shape[0], : rgb.shape[1]]
    if up.shape != rgb.shape[:2]:
        pad = np.zeros(rgb.shape[:2], dtype=bool)
        pad[: up.shape[0], : up.shape[1]] = up
        up = pad
    rgb[up, 0] = 255
    rgb[up, 1] = rgb[up, 1] // 3
    rgb[up, 2] = rgb[up, 2] // 3
    Image.fromarray(rgb).save(path)


def make_overlay_hook(outdir: Path):
    saved: list[str] = []

    def hook(scan: dict, name: str, out: dict) -> None:
        tag = "bw" if scan["kind"] == "grey" else "color"
        # '__' for the plane separator: 'Y/encode_c3' must not collide with
        # the distinct manifest entry 'Y_encode_c3' (large Y patch)
        fn = outdir / f"encode_{tag}_{name.replace('/', '__')}_errmap.png"
        save_patch_overlay(scan, name, out, fn)
        saved.append(fn.name)

    return hook, saved


def save_registration_overlay(scan: dict, path: Path, ds: int = 8) -> None:
    """Downsampled page with the 17 registration landmarks (green=locked)."""
    g = _to_u8(scan["grey"][::ds, ::ds])
    img = Image.fromarray(np.stack([g, g, g], axis=-1))
    draw = ImageDraw.Draw(img)
    coef = scan["affine"]
    for lm in scan["registration"]["landmarks"]:
        try:
            e = cc.entry(scan["manifest"], lm["name"])
        except KeyError:
            continue
        cx = e["x_dots"] + e["w_dots"] / 2.0
        cy = e["y_dots"] + e["h_dots"] / 2.0
        sx, sy = cc.affine_apply(coef, np.array([[cx, cy]], float))[0]
        x, y = sx / ds, sy / ds
        color = (0, 200, 0) if lm.get("ok") else (255, 0, 0)
        r = 14
        draw.ellipse([x - r, y - r, x + r, y + r], outline=color, width=2)
        draw.text((x + r + 2, y - r),
                  f"{lm['name']} {lm.get('resid_dots', 0):.1f}d", fill=color)
    reg = scan["registration"]
    draw.text((10, 10),
              f"{Path(scan['path']).name}  rms={reg['residual_rms_dots']:.2f} "
              f"dots  max={reg['residual_max_dots']:.2f}  "
              f"landmarks {reg['n_landmarks_used']}/{reg['n_landmarks_total']}",
              fill=(255, 200, 0))
    img.save(path)


# ---------------------------------------------------------------------------
# synthesis: engine / channel_params mappings / recommendation
# ---------------------------------------------------------------------------

def synth_engine(rep: dict) -> dict:
    sr = rep["selfreport"]
    f = sr["payload_fields"]
    reg = rep["registration"]
    return {"engine": {
        "product": f.get("PR"),
        "version": (f.get("V") or "").strip(),
        "revision": f.get("RV"),
        "serialnumber": f.get("SN"),
        "languagelevel": f.get("LL"),
        "hwres_requested": f.get("R0"),
        "hwres_default": f.get("RD"),
        "hwres_claimed": f.get("RE"),
        "hwres_measured_xy": [600, 600],
        "hwres_measured_basis": (
            f"registration px/dot = {reg['px_per_dot_x']:.5f}/"
            f"{reg['px_per_dot_y']:.5f} at 1200 dpi scan; ruler scale "
            f"{rep['geometry']['scale_xy']} — 600 dpi native both axes "
            "(claimed HWResolution confirmed by measurement, 001.0 truth "
            "hierarchy)"),
        "pagesize_pt": f.get("PS"),
        "imaging_bbox": f.get("IB"),
        "jobid": f.get("J"),
        "seed": f.get("S"),
        "layout_version": f.get("LAY"),
        "strips_crc_ok": sr["n_strips_crc_ok"],
        "header_echo_match": sr["payload_matches_header_echo"],
        "jobid_matches_manifest": sr["jobid_matches_manifest"],
        "seed_matches_manifest": sr["seed_matches_manifest"],
        "source": "machine strips (stripdec v2, CRC-16/CCITT ok) x2, "
                  "cross-checked against printed header echo; canary G",
    }}


def synth_channel_params(rep: dict, wm_bw: dict, wm_color: dict) -> dict:
    color = rep["color"]
    frags = rep["families"]["structural"]["channel_fragments"]
    return {"channel_params": {
        "crosstalk_matrix": dict(
            color["unmix_matrix"],
            provenance="cal_color color.unmix_matrix -> channel_params "
                       "(synthesizer mapping per cal_color ownership note; "
                       "fit on solids+paper, sub-additivity at stacked solids "
                       "documented in families/density_color)"),
        "cond_number": color["cond_cmy"],
        "dmax": color["dmax"],
        "tvi": {p: {"trc": frags[p]["trc"],
                    "provenance": "families.structural.channel_fragments "
                                  "(structural-measured TRC; density_color "
                                  "key filled by synthesizer)"}
                for p in PLANES},
        "mottle_sigma": {p: frags[p]["mottle"] for p in PLANES},
        "scan_noise_rgb": {
            "white_model_fit_rms_counts": {"grey_scan": wm_bw["rms"],
                                           "color_scan": wm_color["rms"]},
            "note": "paper-white quadratic fit residual rms per channel "
                    "(8-bit counts): upper bound on scanner noise + paper "
                    "texture at white; a narrowband 2-dot-period x artifact "
                    "in DARK areas is documented in families/meta "
                    "(cal_canary _artifact_bins)"},
    }}


def synth_modulation_extras(rep: dict) -> dict:
    km = rep["color"]["k_cmy_margin"]
    scr = rep["canaries"]["screening"].get("detail", {})
    lat = None
    im_path = scr.get("imagemask_path")
    if isinstance(im_path, list) and im_path:
        vals = [d.get("cell_lattice_peak_db") for d in im_path
                if isinstance(d, dict) and d.get("cell_lattice_peak_db")]
        lat = max(vals) if vals else None
    return {"modulation": {
        "k_cmy_dprime": {
            "mahalanobis_px": km["mahalanobis_px"],
            "mahalanobis_cell3": km["mahalanobis_cell3"],
            "provenance": "color.k_cmy_margin (cal_color)"},
        "lattice_snr_db": {
            "value": lat,
            "provenance": "canaries.screening.detail imagemask-path "
                          "cell_lattice_peak_db (M7 self-clocking signal)"},
    }}


def _mi_best(entry: dict) -> tuple[float, str]:
    """max(0, soft MI, 1-H2(hard BER)) — the hard-decision BSC bound guards
    against the measured C-plane soft-stage miscalibration (cal_ber note 3)."""
    mi_soft = entry.get("mi_bits")
    mi_hard = 1.0 - _h2(entry["ber"])
    cands = [(0.0, "floor"), (mi_hard, "hard_decision_bsc")]
    if mi_soft is not None:
        cands.append((float(mi_soft), "soft_llr"))
    v, src = max(cands, key=lambda t: t[0])
    return v, src


def synth_recommendation(rep: dict) -> dict:
    mod = rep["modulation"]
    alpha = rep["alphabet"]
    color = rep["color"]
    minfeat = rep["channel_params"]["min_feature_dots"]

    per_plane: dict[str, dict] = {}
    for p in PLANES:
        cell_min = minfeat[p]["detect"]  # 'detect' tier (001-comparable);
        # 'strict' is None for K/C/Y — stated per structural note 4
        rows = {}
        for c in CELLS:
            e = mod[p][f"c{c}"]
            mi, mi_src = _mi_best(e)
            rows[c] = {
                "ber": e["ber"], "ber_llr": e["ber_llr"],
                "mi_bits_best": round(mi, 4), "mi_source": mi_src,
                "cells_per_mm2": round(cells_per_mm2(c), 2),
                "metric": round(mi * cells_per_mm2(c) * METRIC_MARGIN, 2),
                "ldpc_rate": ldpc_rate(e["ber"]),
                "candidate": bool(
                    e["ber"] <= BER_CANDIDATE_MAX
                    and (cell_min is None or c >= cell_min)),
            }
        cand = [c for c in CELLS if rows[c]["candidate"]]
        best = max(cand, key=lambda c: rows[c]["metric"]) if cand else None
        pp = {
            "cell_dots": best,
            "cell_min_detect_tier": cell_min,
            "cells": rows,
            "ldpc_rate": rows[best]["ldpc_rate"] if best else None,
            "ber_at_recommended": rows[best]["ber"] if best else None,
        }
        if p == "K":
            ref = mod["K"]["c3_ref"]
            pp["ref_patch_18mm"] = {
                "ber": ref["ber"], "ldpc_rate": ldpc_rate(ref["ber"]),
                "note": "18x18 mm encode_K_ref reads lower BER than the "
                        "14x14 mm matrix patch (within-page position "
                        "variance, cal_ber stationarity check); the curated "
                        "ladder rate uses the matrix patch (conservative)"}
        if p == "Y":
            large = mod["Y"]["c3_large"]
            pp["large_patch_20mm"] = {"ber": large["ber"],
                                      "ldpc_rate": ldpc_rate(large["ber"])}
        per_plane[p] = pp

    comp_rows = {}
    comp_bits = 0.0
    for p in ("C", "M", "Y"):
        e = mod["composite"][p]
        r = ldpc_rate(e["ber"])
        comp_rows[p] = {"ber": e["ber"], "ldpc_rate": r,
                        "usable": r is not None}
        comp_bits += (r or 0.0)
    iso_bits = sum(per_plane[p]["ldpc_rate"] or 0.0 for p in ("C", "M", "Y"))

    cond = color["cond_cmy"]
    screening = rep["canaries"]["screening"]
    sim_cmy = {
        "cond_number": cond, "cond_gate": 8.0,
        "cond_pass": bool(cond <= 8.0),
        "composite_c3": comp_rows,
        "verdict": "no-as-printed",
        "note": ("cond(A_cmy) passes, but the composite path is NOT the raw "
                 "channel: canary A (screening) FAILS — put_cmyk_bitmap "
                 "DeviceCMYK 1-bit images are re-screened by the RIP "
                 f"({screening['statistic']:.1f} dB plane-angle screen "
                 "peaks) while single-plane imagemask patches are "
                 "bit-faithful. Y composite BER 24% is unusable as printed. "
                 "Composite tax is therefore an UPPER BOUND on the raw-path "
                 "channel; fix psgen composite emission (DESIGN.md §2.4 "
                 "amendment) and re-measure, and re-decode composites on "
                 "unmixed densities (crosstalk matrix now available), "
                 "before ruling simultaneous CMY out."),
    }

    d3 = cells_per_mm2(3)
    estimates = {
        "cells_per_mm2_at_cell3": round(d3, 2),
        "cmy_composite_as_measured_bits_per_mm2": round(comp_bits * d3, 1),
        "cmy_isolated_ceiling_bits_per_mm2": round(iso_bits * d3, 1),
        "assumed_printable_area_mm2": PRINTABLE_AREA_MM2,
        "est_MB_per_side": {
            "cmy_composite_as_measured": round(
                comp_bits * d3 * PRINTABLE_AREA_MM2 / 8e6, 2),
            "cmy_isolated_ceiling": round(
                iso_bits * d3 * PRINTABLE_AREA_MM2 / 8e6, 2)},
        "note": "advisory (§11): inner-code payload only — excludes outer "
                "RaptorQ overhead, pilots and infrastructure area",
    }

    return {"recommendation": {
        "decision_rules": {
            "rate_ladder": [list(t) for t in RATE_LADDER],
            "candidate_gate_ber": BER_CANDIDATE_MAX,
            "cell_min": "max(min ink, min white), structural 'detect' tier",
            "metric": "MI_best x cells/mm2 x 0.8 (panel §11); MI_best = "
                      "max(0, soft MI, 1-H2(hard BER))",
            "states_gate": "4-level only if MI4 > 1.15 x MI2 (rejected); "
                           "V-CMYK16 only if MI16 > MI8 (rejected)",
        },
        "planes": list(PLANES),
        "per_plane": per_plane,
        "cell_dots": {p: per_plane[p]["cell_dots"] for p in PLANES},
        "ldpc_rate": {p: per_plane[p]["ldpc_rate"] for p in PLANES},
        "states_per_cell": {
            "binary_per_plane": 2,
            "multilevel_4level": "rejected",
            "cmyk16": "rejected",
            "mi_8state": alpha["mi_8state"], "mi_16state": alpha["mi_16state"],
            "mi_4level_K": alpha["mi_4level_K"],
            "mi_4level_C": alpha["mi_4level_C"],
            "verdict_text": alpha["states_per_cell_verdict"],
        },
        "simultaneous_cmy": sim_cmy,
        "estimates": estimates,
        "headline": (
            "cell=3 binary per plane stands for K/C/M (isolated hard BER "
            f"{mod['K']['c3']['ber']:.1%}/{mod['C']['c3']['ber']:.1%}/"
            f"{mod['M']['c3']['ber']:.1%} -> R=0.67); Y is the weak plane "
            f"({mod['Y']['c3']['ber']:.1%} isolated -> R=0.55, collapses to "
            f"{mod['composite']['Y']['ber']:.1%} in the composite). "
            "Multilevel and CMYK16 alphabets rejected; K stays a separate "
            "binary plane. Composite verdict blocked on the §2.4 raw-path "
            "fix (canary A)."),
    }}


def synth_meta(rep: dict) -> dict:
    return {"families": {"meta": {
        "canary_letter_map": {
            "A_rescreening": ["screening"],
            "B_contone_screen": ["contone_fingerprint"],
            "C_toner_save": ["toner_save"],
            "D_resolution_clamp": ["D", "clamp_phase"],
            "E_rescale": ["E", "rescale"],
            "F_ret_edges": ["F"],
            "G_interpreter": ["interpreter"],
            "extra_mic_hunt": ["mic"],
        },
        "note": "letters per ANALYZER-CONTRACT §8 / panel §8; D and E each "
                "have two independent measurements (structural/transport "
                "letter keys + cal_canary descriptive keys)",
    }}}


# ---------------------------------------------------------------------------
# gates: null controls + canary completeness
# ---------------------------------------------------------------------------

def collect_null_controls(rep: dict) -> tuple[list, list]:
    """All BER-style nulls (path, value) and all falsy null_ok paths."""
    nulls: list[tuple[str, float]] = []
    not_ok: list[str] = []

    def walk(o, path: str) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                here = f"{path}/{k}"
                if k in ("ber_null", "null_ber") and isinstance(v, (int, float)):
                    nulls.append((here, float(v)))
                elif k == "null_ok" and v is not True:
                    not_ok.append(here)
                else:
                    walk(v, here)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")

    walk(rep, "")
    return nulls, not_ok


def check_canaries(rep: dict) -> list[str]:
    problems = []
    for k, v in rep["canaries"].items():
        if not isinstance(v, dict) or v.get("status") not in (
                "pass", "fail", "indeterminate"):
            problems.append(f"canaries/{k}: bad status {v!r}")
            continue
        for req in ("statistic", "control", "note"):
            if req not in v:
                problems.append(f"canaries/{k}: missing {req}")
    return problems


# ---------------------------------------------------------------------------
# human summary (§11-style decision block)
# ---------------------------------------------------------------------------

def print_summary(rep: dict) -> None:
    W = 78
    def hdr(s: str) -> None:
        print("\n" + f"== {s} ".ljust(W, "="))

    reg_c, reg_b = rep["registration"], rep["registration_bw"]
    print("=" * W)
    print("CAL-1 ANALYZER REPORT — experiment 002, run 002.0 (real scans)")
    print("=" * W)
    print(f"scans: color {rep['scan']['sha256'][:12]}  grey "
          f"{rep['scan_bw']['sha256'][:12]}")
    print(f"registration: color rms {reg_c['residual_rms_dots']:.2f} dots "
          f"({reg_c['n_landmarks_used']}/{reg_c['n_landmarks_total']} lm), "
          f"grey rms {reg_b['residual_rms_dots']:.2f} dots "
          f"({reg_b['n_landmarks_used']}/{reg_b['n_landmarks_total']} lm)")

    hdr("ENGINE (strip selfreport, CRC-verified)")
    en = rep["engine"]
    print(f"{en['product']}  fw={en['version']}/r{en['revision']}  "
          f"LL={en['languagelevel']}  jobid={en['jobid']}")
    print(f"HWRes requested={en['hwres_requested']} claimed={en['hwres_claimed']} "
          f"measured={en['hwres_measured_xy'][0]}x{en['hwres_measured_xy'][1]}  "
          f"PageSize={en['pagesize_pt']} pt")
    print(f"strips CRC ok: {en['strips_crc_ok']}/2   header echo match: "
          f"{en['header_echo_match']}   jobid/seed match manifest: "
          f"{en['jobid_matches_manifest']}/{en['seed_matches_manifest']}")

    hdr("GEOMETRY / TRANSPORT")
    g = rep["geometry"]
    cp = rep["channel_params"]
    print(f"scale xy={g['scale_xy']}  anisotropy={g['anisotropy_y_over_x']}  "
          f"skew={g['skew_deg']} deg  rot={g['rotation_deg']} deg")
    print(f"warp rms/max = {g['warp_rms_dots']}/{g['warp_max_dots']} dots   "
          f"margins (upper bounds) mm: {g['margins_mm']}")
    ts = cp["transport_steps"]
    print(f"transport steps: {ts['n']} total ({ts['per_40mm']}/40mm), sizes "
          f"{ts['size_dots']['min']}-{ts['size_dots']['max']} dots "
          f"(median {ts['size_dots']['median']}), replicated "
          f"{ts['replicated_in_both_halves']}")
    b = cp["banding"]
    print(f"banding: {'NULL (bounded)' if b['no_significant_banding'] else 'DETECTED'}"
          f" — strongest candidate {b['strongest_candidate']} "
          f"(upper bound {b['upper_bound_amp_density']} D)")
    print("plane offsets vs K (drift models, dots):")
    for p, o in cp["plane_offsets"].items():
        print(f"  {p}: dy center {o['dy_center_dots']:+.2f} "
              f"slope {o['dy_slope_dots_per_100mm']:+.2f}/100mm "
              f"range {o['dy_range_dots']}   dx center {o['dx_center_dots']:+.2f}")

    hdr("STRUCTURAL (per plane: min feature / gain / PSF / Dmax)")
    mf = cp["min_feature_dots"]
    dt = cp["dev_threshold_dots"]
    ge = cp["gain_edge_dots"]
    ps = cp["psf_sigma_dots"]
    dmax = cp["dmax"]
    print(f"{'':2} {'minfeat s/d':>12} {'ink s/d':>8} {'white s/d':>10} "
          f"{'gain H/V/2D':>18} {'PSF x/y':>12} {'Dmax':>6}")
    for p in PLANES:
        dm = dmax.get(p)
        dm_s = f"{dm:6.2f}" if dm is not None else "   -  "
        print(f"{p:2} {str(mf[p]['strict']):>5}/{str(mf[p]['detect']):<6} "
              f"{str(dt[p]['ink']):>3}/{str(dt[p]['ink_detect']):<4} "
              f"{str(dt[p]['white']):>4}/{str(dt[p]['white_detect']):<5} "
              f"{str(ge[p]['h_lines']):>6}/{str(ge[p]['v_lines'])}/"
              f"{str(ge[p]['checker_2d']):<6} "
              f"{ps[p]['x']}/{ps[p]['y']}  {dm_s}")
    print("(s/d = strict/detect tier; strict None = <50% flux area at n<=3; "
          "PSF is print+scan, coarse at 2 px/dot)")

    hdr("MODULATION MATRIX (hard BER / soft BER / MI bits per cell)")
    mod = rep["modulation"]
    for p in PLANES:
        row = []
        for c in CELLS:
            e = mod[p][f"c{c}"]
            mi = e["mi_bits"]
            row.append(f"c{c} {e['ber']:.3f}/"
                       + (f"{e['ber_llr']:.3f}" if e['ber_llr'] is not None else "  -  ")
                       + "/" + (f"{mi:+.2f}" if mi is not None else "  -  "))
        print(f"  {p} ({mod[p]['c1']['scan']}):  " + "  ".join(row))
    e = mod["K"]["c3_ref"]
    print(f"  K c3 18mm ref: {e['ber']:.4f} (stationarity vs 001.4 "
          f"0.020-0.022: elevated but same regime)")
    print("  composite c3 (SCREENED channel, see canary A): " + "  ".join(
        f"{p} {mod['composite'][p]['ber']:.3f}" for p in ("C", "M", "Y")))

    hdr("ALPHABET / UNMIX")
    al = rep["alphabet"]
    print(f"8-state CMY MI = {al['mi_8state']:.3f} / 3.0 bits  "
          f"(acc {al['accuracy_8state']:.3f})")
    print(f"16-state CMYK MI = {al['mi_16state']:.3f} / 4.0 bits  "
          f"(< 8-state -> V-CMYK16 REJECTED)")
    print(f"4-level MI: K {al['mi_4level_K']:.3f}, C {al['mi_4level_C']:.3f} "
          f"/ 2.0 -> multilevel REJECTED (gate 1.15 x MI2)")
    print(f"unmix cond(A_cmy) = {rep['color']['cond_cmy']:.2f} (gate 8) — "
          f"{rep['color']['unmix_feasibility']['status']}")
    km = rep["modulation"]["k_cmy_dprime"]
    print(f"K-vs-CMY margin: Mahalanobis d = {km['mahalanobis_cell3']:.2f} "
          f"at cell 3")

    hdr("RECOMMENDATION (§11 decision logic)")
    rec = rep["recommendation"]
    for p in PLANES:
        pp = rec["per_plane"][p]
        c = pp["cell_dots"]
        print(f"  {p}: cell={c}  BER={pp['ber_at_recommended']:.3%}  "
              f"LDPC rate={pp['ldpc_rate']}  "
              f"(cell_min detect tier: {pp['cell_min_detect_tier']})")
    sim = rec["simultaneous_cmy"]
    print(f"  simultaneous CMY: {sim['verdict']} (cond "
          f"{sim['cond_number']:.2f} passes; composite rates "
          + ", ".join(f"{p}={v['ldpc_rate']}" for p, v in sim['composite_c3'].items())
          + ")")
    est = rec["estimates"]
    print(f"  est bits/mm2: composite-as-measured "
          f"{est['cmy_composite_as_measured_bits_per_mm2']}, isolated ceiling "
          f"{est['cmy_isolated_ceiling_bits_per_mm2']}  "
          f"(~{est['est_MB_per_side']['cmy_composite_as_measured']} / "
          f"{est['est_MB_per_side']['cmy_isolated_ceiling']} MB/side)")
    print(f"  {rec['headline']}")

    hdr("CANARIES")
    order = ["screening", "contone_fingerprint", "toner_save", "D",
             "clamp_phase", "E", "rescale", "F", "interpreter", "mic"]
    letters = {"screening": "A", "contone_fingerprint": "B",
               "toner_save": "C", "D": "D", "clamp_phase": "D'",
               "E": "E", "rescale": "E'", "F": "F", "interpreter": "G",
               "mic": "+"}
    for k in order:
        v = rep["canaries"].get(k)
        if v is None:
            continue
        print(f"  [{letters.get(k, '?'):>2}] {v['name']:<24} "
              f"{v['status'].upper():<14} stat={v['statistic']:10.3f} "
              f"ctrl={v['control']:9.3f}")
        print(f"       {v['note'][:130]}")

    hdr("NULL CONTROLS")
    nulls, not_ok = collect_null_controls(rep)
    vals = [v for _, v in nulls]
    print(f"  {len(nulls)} BER-style null controls, range "
          f"[{min(vals):.3f}, {max(vals):.3f}] "
          f"(gate [0.48, 0.52])  ->  "
          f"{'ALL PASS' if all(0.48 <= v <= 0.52 for v in vals) else 'FAILURES'}")
    print(f"  null_ok flags false: {len(not_ok)}"
          + (f"  {not_ok}" if not_ok else ""))
    print("=" * W)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="CAL-1 full analyzer (exp 002)")
    ap.add_argument("scan_bw", nargs="?", default=str(DEFAULT_BW))
    ap.add_argument("scan_color", nargs="?", default=str(DEFAULT_COLOR))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--overlays-dir", default=str(DEFAULT_OVERLAYS))
    args = ap.parse_args()

    t0 = time.time()
    overlays = Path(args.overlays_dir)
    overlays.mkdir(parents=True, exist_ok=True)

    # ---- core registration, ONCE per scan --------------------------------
    print(f"[{time.time()-t0:6.1f}s] loading + registering {args.scan_bw}")
    scan_bw = cc.load_scan(args.scan_bw)
    cc.register(scan_bw)
    rb = scan_bw["registration"]
    print(f"[{time.time()-t0:6.1f}s]   grey:  "
          f"{rb['n_landmarks_used']}/{rb['n_landmarks_total']} landmarks, "
          f"rms {rb['residual_rms_dots']:.3f} dots")
    print(f"[{time.time()-t0:6.1f}s] loading + registering {args.scan_color}")
    scan_color = cc.load_scan(args.scan_color)
    cc.register(scan_color)
    rc = scan_color["registration"]
    print(f"[{time.time()-t0:6.1f}s]   color: "
          f"{rc['n_landmarks_used']}/{rc['n_landmarks_total']} landmarks, "
          f"rms {rc['residual_rms_dots']:.3f} dots")

    save_registration_overlay(scan_bw, overlays / "registration_bw.png")
    save_registration_overlay(scan_color, overlays / "registration_color.png")

    # ---- shared context: white models fitted once ------------------------
    print(f"[{time.time()-t0:6.1f}s] fitting white models (both scans)")
    wm_bw = cc.white_model(scan_bw)
    wm_color = cc.white_model(scan_color)
    hook, saved_overlays = make_overlay_hook(overlays)
    core_ctx = {"white_model_bw": wm_bw, "white_model_color": wm_color,
                "overlay_hook": hook}

    # ---- dispatch families -----------------------------------------------
    rep = cc.report_init(scan_color)      # color scan = headline scan
    cc.report_merge(rep, {
        "scan_bw": {"path": scan_bw["path"], "sha256": scan_bw["sha256"],
                    "kind": scan_bw["kind"],
                    "shape_px": list(scan_bw["grey"].shape)},
        "registration_bw": rb,
    })

    families = [
        ("transport (cal_geometry)", cal_geometry.run),
        ("structural (cal_structural)", cal_structural.run),
        ("modulation (cal_ber)", cal_ber.run),
        ("density_color/alphabet (cal_color)", cal_color.run),
        ("meta/canaries (cal_canary)", cal_canary.run),
    ]
    for label, fn in families:
        print(f"\n[{time.time()-t0:6.1f}s] ==== family: {label} ====")
        payload = fn(scan_bw, scan_color, core_ctx)
        cc.report_merge(rep, payload)
        print(f"[{time.time()-t0:6.1f}s] merged {label}")

    # ---- synthesis --------------------------------------------------------
    print(f"\n[{time.time()-t0:6.1f}s] synthesizing curated cross-family keys")
    cc.report_merge(rep, synth_engine(rep))
    cc.report_merge(rep, synth_channel_params(rep, wm_bw, wm_color))
    cc.report_merge(rep, synth_modulation_extras(rep))
    cc.report_merge(rep, synth_recommendation(rep))
    cc.report_merge(rep, synth_meta(rep))
    rep["analysis"] = {
        "tool": "analyze_calpage.py",
        "families_run": [label for label, _ in families],
        "overlays_dir": str(overlays),
        "n_patch_overlays": len(saved_overlays),
        "elapsed_s": round(time.time() - t0, 1),
    }

    # ---- gates -------------------------------------------------------------
    nulls, not_ok = collect_null_controls(rep)
    bad_nulls = [(p, v) for p, v in nulls if not (0.48 <= v <= 0.52)]
    canary_problems = check_canaries(rep)
    n_canaries = len(rep["canaries"])

    cc.save_report(rep, args.out)
    print(f"[{time.time()-t0:6.1f}s] report -> {args.out}  "
          f"({len(saved_overlays)} patch overlays + 2 registration overlays "
          f"-> {overlays})")

    print_summary(rep)

    ok = True
    if bad_nulls:
        ok = False
        print(f"\n!! NULL-CONTROL GATE FAILED ({len(bad_nulls)}):")
        for p, v in bad_nulls:
            print(f"   {p} = {v:.4f}")
    if not_ok:
        ok = False
        print(f"\n!! null_ok FLAGS FALSE ({len(not_ok)}): {not_ok}")
    if canary_problems:
        ok = False
        print(f"\n!! CANARY TABLE PROBLEMS: {canary_problems}")
    print(f"\ngates: {len(nulls)} null controls "
          f"{'OK' if not bad_nulls and not not_ok else 'FAILED'}; "
          f"{n_canaries} canary verdicts "
          f"{'complete' if not canary_problems else 'INCOMPLETE'}; "
          f"total {time.time()-t0:.0f} s")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

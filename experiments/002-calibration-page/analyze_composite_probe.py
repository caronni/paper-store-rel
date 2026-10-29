#!/usr/bin/env python
"""analyze_composite_probe.py — experiment 002.1: composite emission probe.

Which PostScript emission path prints overlapping CMY planes bit-faithfully on
the M281 RIP? Analyzes the ONE probe sheet of gen_composite_probe.py against
build/composite_probe_manifest.json + per-plane INTENT ground truth, per the
decision rule in build/PROTOCOL-002.1-draft.md.

Three discriminators, identical analysis parameters for every variant P0-P4
(no per-variant tuning; P0 is the known-screened positive control):

  1. SCREENING  — canary-A 2-D spectrum method ported from cal_canary.py
     (_excess_db / lattice + scan-chain bin exclusion / GT-spectrum control),
     per printed field, plus a quiet-zone control window per channel.
     GT-spectrum controls are cached: per-plane content is byte-identical
     across P0-P3 by construction (asserted at startup).
  2. KNOCKOUT   — per-plane v4 decode (cc.decode_patch, soft stage off) of the
     CM / CMY fields; cell errors split by the OTHER plane's GT (miss rate at
     overlap vs clear sites). Solid CM patch: C-presence under M from
     r-channel density arithmetic vs the P4 C100/M100 references.
  3. BER        — per-plane hard BER of every variant field vs the P4
     single-plane reference fields on the same scan (gate: ref + 0.02).

Null control (001.2 discipline) on every field decode: decoded bits vs the
8-cell-shifted GT must read 0.50 +- 0.02 or the number is invalid.

Decode primitives go exclusively through cal_core (frozen contract; the probe
manifest is passed explicitly — cal_core itself is untouched).

Determinism: no randomness anywhere in this module.

Run (repo root, ~5-8 min):
  env/bin/python experiments/002-calibration-page/analyze_composite_probe.py \
      <evidence>/scans/test-scan-composite-probe.png
Outputs: build/composite_probe_report.json + human summary on stdout.
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
from scipy import ndimage

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import cal_core as cc  # noqa: E402  (frozen analyzer core — do not edit)

MANIFEST_PATH = cc.BUILD / "composite_probe_manifest.json"
EXPECTED_SCAN_SHA256 = ("c0187114827938058bf11d2c1b5c4cd0710ca2566e"
                        "74b424fff547b0d7c05a8a")

OVERLAP_VARIANTS: tuple[str, ...] = ("P0", "P1", "P2", "P3")
CELL_DOTS = 3

# ---- fixed analysis gates (identical for every variant; from the protocol +
# ---- cal_canary calibration; see PROTOCOL-002.1-draft.md) -------------------
SCREEN_STRONG_DB = 18.0        # one peak this high = screened (cal_canary rule)
SCREEN_COHERENT_DB = 12.0      # hit threshold (chance floor of the disk stat ~9-11 dB)
DISK_TOL_CPD = 0.02            # cal_canary._excess_at disk radius

# Device screen-family fingerprints (cyc/dot; sign mirrors are searched, so one
# entry covers the +-angle pair). 165/212: measured in 002.0 (canary A/B) on
# put_cmyk_bitmap composites. 224 @ 26.6 deg (rational tangent 1/2, (1/3,1/6)):
# measured HERE and cross-checked on the 002.0 scan (see XCHECK_002_0): present
# in single-plane Y imagemask fields on BOTH sheets — a pre-existing Y-plane
# property, NOT an overlap-path effect. Note the Y contone screen (~200 lpi
# @ ~0 deg per HP convention) sits ON the cell=3 lattice bins (1/3, 0) and is
# structurally invisible to every off-lattice statistic in this suite.
SCREEN_FAMILIES: dict[str, tuple[float, float]] = {
    "165lpi_pm14deg": (0.266, 0.068),
    "212lpi_45deg": (0.25, 0.25),
    "224lpi_pm27deg": (1.0 / 3.0, 1.0 / 6.0),
}

# 002.0 cross-check (same statistic, this module, ad-hoc run 2026-07-04 on
# scans/test-scan-calpage-color.png sha 2bbb8704...30a9f6, registration RMS
# 1.90 dots): family disk excess dB (GT floor in parens). Regenerate with
# --xcheck-calpage. Reading: single-plane C/M imagemask clean at every family;
# single-plane Y imagemask carries 224 (and 165-disk leakage of it) on the
# 002.0 sheet ALREADY; put_cmyk_bitmap composites carry 165+212 but NOT 224.
XCHECK_002_0: dict = {
    "scan": "scans/test-scan-calpage-color.png",
    "scan_sha256_prefix": "2bbb87042851dae0",
    "statistic": "disk_excess tol 0.02 cyc/dot, this module",
    "patches": {
        "C/encode_c3": {"ch": "r", "165lpi_pm14deg": 9.4, "224lpi_pm27deg": 8.5,
                        "212lpi_45deg": 8.9, "gt_floors": [9.9, 9.4, 10.4]},
        "M/encode_c3": {"ch": "g", "165lpi_pm14deg": 9.1, "224lpi_pm27deg": 8.9,
                        "212lpi_45deg": 9.5, "gt_floors": [10.2, 7.8, 10.3]},
        "Y/encode_c3": {"ch": "b", "165lpi_pm14deg": 19.3, "224lpi_pm27deg": 21.1,
                        "212lpi_45deg": 10.5, "gt_floors": [9.8, 9.4, 9.5]},
        "Y_encode_c3": {"ch": "b", "165lpi_pm14deg": 21.8, "224lpi_pm27deg": 23.5,
                        "212lpi_45deg": 18.5, "gt_floors": [9.8, 11.8, 9.9]},
        "composite_c3_C": {"ch": "r", "165lpi_pm14deg": 22.6, "224lpi_pm27deg": 10.4,
                           "212lpi_45deg": 20.8, "gt_floors": [11.3, 10.3, 11.1]},
        "composite_c3_M": {"ch": "g", "165lpi_pm14deg": 24.6, "224lpi_pm27deg": 11.7,
                           "212lpi_45deg": 22.5, "gt_floors": [9.8, 8.6, 10.1]},
        "composite_c3_Y": {"ch": "b", "165lpi_pm14deg": 18.1, "224lpi_pm27deg": 10.9,
                           "212lpi_45deg": 19.9, "gt_floors": [9.9, 9.8, 10.6]},
    },
}
REG_RMS_GATE_DOTS = 3.0
NULL_TOL = 0.02
KNOCKOUT_MISS_GATE = 0.40      # miss rate at overlap ink sites under knockout ~0.5-1.0
KNOCKOUT_MISS_RATIO = 3.0      # ... and >= 3x the clear-site miss rate
PRESENCE_KNOCKOUT_MAX = 0.25   # solid C-presence index below this = knocked out
PRESENCE_PRESERVED_MIN = 0.50  # ... above this = both inks present
BER_GATE_ABS = 0.02            # variant field BER <= P4 ref BER + this

# under-plane map for the knockout splits: (field, decoded plane) -> planes
# painted LATER (paint order C, M, Y; later paint can knock out earlier).
UNDER_PLANES: dict[tuple[str, str], tuple[str, ...]] = {
    ("field_cm", "C"): ("M",),
    ("field_cm", "M"): (),           # top plane — control split vs C below
    ("field_cmy", "C"): ("M", "Y"),
    ("field_cmy", "M"): ("Y",),
    ("field_cmy", "Y"): (),
}
FIELD_PLANES: dict[str, tuple[str, ...]] = {
    "field_cm": ("C", "M"), "field_cmy": ("C", "M", "Y"),
}
P4_REF_FOR_PLANE = {"C": "P4/ref_C", "M": "P4/ref_M", "Y": "P4/ref_Y"}


# ---------------------------------------------------------------------------
# screening spectra (canary-A method, ported from cal_canary.py — attribution)
# ---------------------------------------------------------------------------

def _hann2(shape: tuple[int, int]) -> np.ndarray:
    return np.outer(np.hanning(shape[0]), np.hanning(shape[1]))


def _excess_db(a: np.ndarray, med_size: int = 15
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(excess_db, fx, fy): 2-D magnitude spectrum in dB above its local
    median background (fftshifted). Frequencies in cycles/dot (sub=2, d=0.5)."""
    a = np.asarray(a, np.float64)
    a = a - a.mean()
    mag = 20.0 * np.log10(np.abs(np.fft.fft2(a * _hann2(a.shape))) + 1e-9)
    mag = np.fft.fftshift(mag)
    bg = ndimage.median_filter(mag, size=med_size, mode="wrap")
    fy = np.fft.fftshift(np.fft.fftfreq(a.shape[0], d=0.5))
    fx = np.fft.fftshift(np.fft.fftfreq(a.shape[1], d=0.5))
    return mag - bg, fx, fy


def _freq_grids(fx: np.ndarray, fy: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    FX, FY = np.meshgrid(fx, fy)
    return FX, FY, np.hypot(FX, FY)


def _lattice_bins(FX: np.ndarray, FY: np.ndarray, cell_dots: int,
                  tol: float = 0.012) -> np.ndarray:
    """Cell-lattice lines (M7 self-clocking signal — expected, not a screen)."""
    def near(F: np.ndarray) -> np.ndarray:
        return np.abs(F - np.round(F * cell_dots) / cell_dots) < tol
    return near(FX) & near(FY)


def _artifact_bins(FX: np.ndarray, FY: np.ndarray,
                   tol: float = 0.012) -> np.ndarray:
    """Measured (+-0.5, ~0) cyc/dot scan-chain line (002.0) — excluded."""
    return (np.abs(np.abs(FX) - 0.5) < tol) & (np.abs(FY) < tol)


def disk_excess(exc: np.ndarray, fx: np.ndarray, fy: np.ndarray,
                f_pk: tuple[float, float], tol: float = DISK_TOL_CPD) -> float:
    """Max spectral excess within a freq disk around f_pk and its sign mirrors
    (ported from cal_canary._excess_at)."""
    FX, FY, _ = _freq_grids(fx, fy)
    best = -np.inf
    for sx in (1, -1):
        for sy in (1, -1):
            d = np.hypot(FX - sx * f_pk[0], FY - sy * f_pk[1])
            best = max(best, float(exc[d < tol].max()))
    return best


def _offgt_stats(exc_print: np.ndarray, exc_gt: np.ndarray | None,
                 fx: np.ndarray, fy: np.ndarray) -> dict:
    """Max off-lattice / off-artifact / off-GT excess of a printed spectrum,
    with GT-spectrum control when a GT raster exists."""
    FX, FY, r = _freq_grids(fx, fy)
    base = (r > 0.04) & (r < 0.9)
    lat = _lattice_bins(FX, FY, CELL_DOTS)
    art = _artifact_bins(FX, FY)
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
    return {
        "max_offgt_peak_db": stat,
        "gt_control_db": ctrl,
        "peak_freq_cyc_per_dot": list(f_pk),
        "peak_lpi": float(math.hypot(*f_pk) * cc.HW_DPI),
        "peak_angle_deg": float(math.degrees(math.atan2(f_pk[1], f_pk[0]))),
        "cell_lattice_peak_db": float(exc_print[base & lat].max()),
        "scanchain_artifact_peak_db": float(exc_print[base & art].max()),
        "n_offgt_bins": int(mask.sum()),
    }


def screening_field(scan: dict, name: str, gt_exc_cache: dict) -> dict:
    """Canary-A screening statistics for one printed field patch: global
    off-GT max (informative) + disk excess at each screen family (judged)."""
    v = cc.patch_view(scan, name)
    exc_p, fx, fy = _excess_db(v.crop())
    key = name.split("/", 1)[1]        # content identical across P0-P3
    if key not in gt_exc_cache:
        gt = cc.load_gt(v.entry)
        gt_raster = np.kron((1.0 - gt).astype(np.float32) * 255.0,
                            np.ones((v.sub, v.sub), np.float32))
        gt_exc_cache[key] = _excess_db(gt_raster)[0]
    exc_g = gt_exc_cache[key]
    st = _offgt_stats(exc_p, exc_g, fx, fy)
    fams = {fam: disk_excess(exc_p, fx, fy, f) for fam, f in SCREEN_FAMILIES.items()}
    floors = {fam: disk_excess(exc_g, fx, fy, f) for fam, f in SCREEN_FAMILIES.items()}
    return {"patch": name, "channel": v.reg_channel,
            "locked": bool(v.local_locked), "q": v.local_quality,
            "family_excess_db": fams, "family_gt_floor_db": floors, **st}


def screening_quiet_zone(scan: dict) -> dict:
    """Off-lattice max + family excess of a field-sized quiet-zone window per
    channel (control bar for the fields; blank paper, no GT term)."""
    v = cc.patch_view(scan, "quiet_zone", local="none")
    out = {}
    n_px = 354 * v.sub                 # field-sized window, matched bin count
    for ch in ("r", "g", "b"):
        a = v.crop(ch)
        y0 = (a.shape[0] - n_px) // 2
        x0 = (a.shape[1] - n_px) // 2
        exc, fx, fy = _excess_db(a[y0: y0 + n_px, x0: x0 + n_px])
        out[ch] = {**_offgt_stats(exc, None, fx, fy),
                   "family_excess_db": {fam: disk_excess(exc, fx, fy, f)
                                        for fam, f in SCREEN_FAMILIES.items()}}
    return out


def variant_screening_verdict(dets: list[dict]) -> dict:
    """Per (family, channel) verdict against the GT chance floor.

    hit    = disk excess >= max(12 dB, GT floor + 6)  (cal_canary leakage rule)
    screened at (family, channel) = any patch >= 18 dB, or >= 2 patches hit
    (coherence across patches; single-patch channels need the strong peak).
    """
    per_fc: dict[str, dict] = {}
    for fam in SCREEN_FAMILIES:
        for ch in sorted({d["channel"] for d in dets}):
            sel = [d for d in dets if d["channel"] == ch]
            excs = [d["family_excess_db"][fam] for d in sel]
            hits = [d for d in sel if d["family_excess_db"][fam]
                    >= max(SCREEN_COHERENT_DB, d["family_gt_floor_db"][fam] + 6.0)]
            strong = any(d["family_excess_db"][fam] >= SCREEN_STRONG_DB for d in sel)
            per_fc[f"{fam}|{ch}"] = {
                "max_db": float(max(excs)), "n_hits": len(hits),
                "n_patches": len(sel),
                "screened": bool(strong or len(hits) >= 2)}
    screened_fc = sorted(k for k, r in per_fc.items() if r["screened"])
    return {"per_family_channel": per_fc, "screened_fc": screened_fc,
            "screened": bool(screened_fc)}


# ---------------------------------------------------------------------------
# knockout splits + BER (v4 hard decode, soft stage off — hard BER suffices)
# ---------------------------------------------------------------------------

def _split(err: np.ndarray, sel: np.ndarray) -> dict:
    n = int(sel.sum())
    return {"err": (float(err[sel].mean()) if n else None), "n_cells": n}


def decode_field(scan: dict, manifest: dict, name: str) -> dict:
    """v4 hard decode + null control + overlap/clear error splits."""
    e = cc.entry(manifest, name)
    t0 = time.time()
    out = cc.decode_patch(scan, e, soft=False, diagnostics=False)
    err = out["err_map"]
    gtb = out["gt_cells"].astype(bool)
    field, plane = name.split("/", 1)[1].rsplit("_", 1)
    rec: dict = {
        "patch": name, "plane": plane, "channel": out["channel"],
        "method": "decode_cells_v4_hard",
        "ber": out["ber"], "n_cells": out["cells"], "errors": out["errors"],
        "clustered": out["clustered"],
        "null_ber": out["ber_null"], "null_ok": out["null_ok"],
        "warp_windows_used": out["warp_windows_used"],
        "warp_windows_total": out["warp_windows_total"],
        "poly_resid_rms_dots": out["poly_resid_rms_dots"],
        "elapsed_s": round(time.time() - t0, 1),
    }
    # splits by the union of LATER-painted planes (knockout discriminator) and,
    # as a crosstalk control, by the union of EARLIER-painted planes.
    variant = name.split("/", 1)[0]
    planes_here = FIELD_PLANES.get(field, ())
    if field in ("field_cm", "field_cmy"):
        order = [p for p in ("C", "M", "Y") if p in planes_here]
        later = UNDER_PLANES[(field, plane)]
        earlier = tuple(p for p in order[: order.index(plane)])

        def union_cells(planes: tuple[str, ...]) -> np.ndarray | None:
            if not planes:
                return None
            u = np.zeros_like(gtb)
            for p in planes:
                sib = cc.entry(manifest, f"{variant}/{field}_{p}")
                u |= cc.load_gt(sib)[::CELL_DOTS, ::CELL_DOTS].astype(bool)
            return u

        for tag, sel_planes in (("under", later), ("over", earlier)):
            u = union_cells(sel_planes)
            if u is None:
                continue
            rec[f"split_{tag}"] = {
                "planes": list(sel_planes),
                "err_overlap": _split(err, u),
                "err_clear": _split(err, ~u),
                "miss_overlap": _split(err, gtb & u),
                "miss_clear": _split(err, gtb & ~u),
                "fa_overlap": _split(err, ~gtb & u),
                "fa_clear": _split(err, ~gtb & ~u),
            }
        if later:
            s = rec["split_under"]
            miss_o = s["miss_overlap"]["err"]
            miss_c = s["miss_clear"]["err"]
            rec["knockout_flag"] = bool(
                miss_o is not None and miss_o >= KNOCKOUT_MISS_GATE
                and miss_o >= KNOCKOUT_MISS_RATIO * max(miss_c or 0.0, 0.01))
    return rec


# ---------------------------------------------------------------------------
# solid densities (density arithmetic — robust on solids)
# ---------------------------------------------------------------------------

def _interior_median_density(scan: dict, wm: dict, entry_name: str) -> dict:
    v = cc.patch_view(scan, entry_name)
    d = cc.density(v, wm, channels=("r", "g", "b"))
    out = {}
    m = v.margin_dots * v.sub
    for ch in ("r", "g", "b"):
        a = d[ch][m: -m or None, m: -m or None]
        h, w = a.shape
        mh, mw = int(h * 0.15), int(w * 0.15)
        out[f"D_{ch}"] = float(np.median(a[mh: h - mh, mw: w - mw]))
    out["locked"] = bool(v.local_locked)
    return out


def solids_analysis(scan: dict, wm: dict) -> dict:
    """CM-solid C-presence-under-M (r channel) vs C100/M100 references."""
    refs = {p: _interior_median_density(scan, wm, f"P4/solid_{p}")
            for p in ("C", "M", "Y")}
    out: dict = {"references_P4": refs}
    for vid in OVERLAP_VARIANTS:
        d = _interior_median_density(scan, wm, f"{vid}/solid_cm_C")
        pres_c = (d["D_r"] - refs["M"]["D_r"]) / max(refs["C"]["D_r"], 1e-6)
        pres_m = (d["D_g"] - refs["C"]["D_g"]) / max(refs["M"]["D_g"], 1e-6)
        if pres_c <= PRESENCE_KNOCKOUT_MAX:
            verdict = "C_knocked_out"
        elif pres_c >= PRESENCE_PRESERVED_MIN:
            verdict = "both_inks_present"
        else:
            verdict = "partial"
        out[vid] = {**d, "presence_C_under_M": float(pres_c),
                    "presence_M_over_C": float(pres_m),
                    "solid_verdict": verdict}
    return out


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def analyze(scan_path: Path, out_path: Path) -> dict:
    t_start = time.time()
    manifest = cc.load_manifest(MANIFEST_PATH)

    # GT identity across P0-P3 (construction invariant the analysis relies on)
    ident = {}
    for base in ("field_cm_C", "field_cm_M", "field_cmy_C", "field_cmy_M",
                 "field_cmy_Y", "solid_cm_C", "solid_cm_M"):
        a0 = cc.load_gt(cc.entry(manifest, f"P0/{base}"))
        ident[base] = all(
            np.array_equal(a0, cc.load_gt(cc.entry(manifest, f"P{v}/{base}")))
            for v in "123")
    if not all(ident.values()):
        raise AssertionError(f"per-plane GT differs across variants: {ident}")

    print(f"loading + registering {scan_path}", flush=True)
    scan = cc.load_scan(scan_path)
    sha_ok = scan["sha256"] == EXPECTED_SCAN_SHA256
    if not sha_ok:
        print(f"!! scan sha256 {scan['sha256']} != expected "
              f"{EXPECTED_SCAN_SHA256}", flush=True)
    reg = cc.register(scan, manifest)
    rms = reg["residual_rms_dots"]
    print(f"  {scan['kind']}, {reg['n_landmarks_used']}/{reg['n_landmarks_total']}"
          f" landmarks, residual RMS {rms:.3f} dots, "
          f"rot {reg['rotation_deg']:.3f} deg, "
          f"px/dot {reg['px_per_dot_x']:.5f}/{reg['px_per_dot_y']:.5f}", flush=True)
    reg_ok = rms is not None and rms < REG_RMS_GATE_DOTS
    if not reg_ok:
        raise cc.RegistrationError(f"residual RMS {rms} >= {REG_RMS_GATE_DOTS}")

    print("white model ...", flush=True)
    wm = cc.white_model(scan)

    # ---- discriminator 1: screening ------------------------------------
    print("screening spectra ...", flush=True)
    gt_exc_cache: dict = {}
    screening: dict = {}
    for vid in OVERLAP_VARIANTS:
        dets = [screening_field(scan, f"{vid}/{f}_{p}", gt_exc_cache)
                for f in ("field_cm", "field_cmy") for p in FIELD_PLANES[f]]
        screening[vid] = {"patches": dets,
                          "verdict": variant_screening_verdict(dets)}
        print(f"  {vid}: screened_fc={screening[vid]['verdict']['screened_fc']}",
              flush=True)
    dets = [screening_field(scan, f"P4/ref_{p}", gt_exc_cache) for p in "CMY"]
    screening["P4"] = {"patches": dets,
                       "verdict": variant_screening_verdict(dets)}
    p4_baseline_fc = set(screening["P4"]["verdict"]["screened_fc"])
    print(f"  P4 baseline screened_fc={sorted(p4_baseline_fc)}", flush=True)
    for vid in OVERLAP_VARIANTS:
        v_ = screening[vid]["verdict"]
        v_["beyond_P4_baseline"] = sorted(
            set(v_["screened_fc"]) - p4_baseline_fc)
    qz = screening_quiet_zone(scan)
    print("  quiet zone off-lattice max: "
          + " ".join(f"{ch}={qz[ch]['max_offgt_peak_db']:.1f}dB"
                     for ch in ("r", "g", "b"))
          + "  family max: "
          + " ".join(f"{ch}:" + ",".join(
              f"{fam[:3]}={qz[ch]['family_excess_db'][fam]:.1f}"
              for fam in SCREEN_FAMILIES) for ch in ("r", "g", "b")), flush=True)

    # ---- discriminators 2+3: field decodes (grouped by scan channel) ---
    print("field decodes (v4 hard, null-controlled) ...", flush=True)
    fields: dict[str, dict] = {}
    groups: list[tuple[str, list[str]]] = [
        ("r", [f"{v}/field_cm_C" for v in OVERLAP_VARIANTS]
              + [f"{v}/field_cmy_C" for v in OVERLAP_VARIANTS] + ["P4/ref_C"]),
        ("g", [f"{v}/field_cm_M" for v in OVERLAP_VARIANTS]
              + [f"{v}/field_cmy_M" for v in OVERLAP_VARIANTS] + ["P4/ref_M"]),
        ("b", [f"{v}/field_cmy_Y" for v in OVERLAP_VARIANTS] + ["P4/ref_Y"]),
    ]
    for ch, names in groups:
        for nm in names:
            rec = decode_field(scan, manifest, nm)
            fields[nm] = rec
            extra = ""
            if "split_under" in rec:
                s = rec["split_under"]
                extra = (f" miss@overlap={s['miss_overlap']['err']:.3f} "
                         f"clear={s['miss_clear']['err']:.3f}"
                         f"{' KNOCKOUT' if rec.get('knockout_flag') else ''}")
            print(f"  {nm:18s} ch={rec['channel']} ber={rec['ber']:.4f} "
                  f"null={rec['null_ber']:.3f}"
                  f"{'' if rec['null_ok'] else ' NULL-FAIL'}{extra}", flush=True)
        scan.get("_f32", {}).pop(ch, None)

    # ---- solids ----------------------------------------------------------
    print("solid densities ...", flush=True)
    solids = solids_analysis(scan, wm)
    r = solids["references_P4"]
    print(f"  refs D_r: C100={r['C']['D_r']:.3f} M100={r['M']['D_r']:.3f}  "
          f"D_g: C100={r['C']['D_g']:.3f} M100={r['M']['D_g']:.3f}", flush=True)
    for vid in OVERLAP_VARIANTS:
        s = solids[vid]
        print(f"  {vid} solid_cm: D_r={s['D_r']:.3f} D_g={s['D_g']:.3f} "
              f"presence_C={s['presence_C_under_M']:.2f} "
              f"presence_M={s['presence_M_over_C']:.2f} -> {s['solid_verdict']}",
              flush=True)

    # ---- verdict assembly (protocol decision rule) -----------------------
    p4_ber = {p: fields[P4_REF_FOR_PLANE[p]]["ber"] for p in "CMY"}
    null_failures = [nm for nm, r_ in fields.items() if not r_["null_ok"]]
    variants: dict[str, dict] = {}
    for vid in OVERLAP_VARIANTS:
        v_fields = {nm: rec for nm, rec in fields.items()
                    if nm.startswith(vid + "/")}
        # protocol rule: no screen-family structure ABOVE the control bar set
        # by the P4 patches (+ quiet zone, reported); the pre-existing Y-plane
        # 224-lpi texture sits in the P4 baseline and is judged separately.
        screen_free = not screening[vid]["verdict"]["beyond_P4_baseline"]
        ko_flags = {nm: rec.get("knockout_flag") for nm, rec in v_fields.items()
                    if "knockout_flag" in rec}
        solid_ko = solids[vid]["solid_verdict"] == "C_knocked_out"
        knockout_free = (not any(ko_flags.values())
                         and solids[vid]["solid_verdict"] == "both_inks_present")
        ber_delta = {nm: rec["ber"] - p4_ber[rec["plane"]]
                     for nm, rec in v_fields.items()}
        ber_ok = all(d <= BER_GATE_ABS for d in ber_delta.values())
        variants[vid] = {
            "screen_free": screen_free,
            "screened_fc": screening[vid]["verdict"]["screened_fc"],
            "screened_beyond_P4": screening[vid]["verdict"]["beyond_P4_baseline"],
            "knockout_flags": ko_flags,
            "solid_verdict": solids[vid]["solid_verdict"],
            "solid_C_knocked_out": solid_ko,
            "knockout_free": knockout_free,
            "ber_delta_vs_P4": ber_delta,
            "ber_within_gate": ber_ok,
            "qualifies": bool(screen_free and knockout_free and ber_ok),
        }

    # positive control: P0 must show RIP-screen structure BEYOND the P4
    # single-plane baseline, or the analysis is broken (protocol rule).
    p0_screened = bool(screening["P0"]["verdict"]["beyond_P4_baseline"])
    adopted = None
    if p0_screened and not null_failures:
        for vid in ("P1", "P2", "P3"):
            if variants[vid]["qualifies"]:
                adopted = vid
                break
    decision = {
        "positive_control_P0_screened": bool(p0_screened),
        "P4_baseline_screened_fc": sorted(p4_baseline_fc),
        "null_control_failures": null_failures,
        "adopted": adopted,
        "rule": "first of P1,P2,P3 that is screen-free (no screened "
                "family|channel beyond the P4 baseline) AND knockout-free AND "
                f"per-plane BER within +{BER_GATE_ABS} of P4 "
                "(PROTOCOL-002.1-draft.md)",
    }
    if not p0_screened:
        decision["note"] = ("POSITIVE CONTROL FAILED: P0 measured screen-free "
                            "— analysis broken, do NOT conclude anything")
    elif adopted is None:
        decision["note"] = ("NO variant qualifies — see per-variant "
                            "characterization (fallback options a/b of the "
                            "protocol apply)")

    report = {
        "run": "002.1",
        "analyzer": "analyze_composite_probe.py",
        "scan": {"path": str(scan_path), "sha256": scan["sha256"],
                 "sha256_expected": EXPECTED_SCAN_SHA256, "sha256_ok": sha_ok,
                 "kind": scan["kind"], "shape_px": list(scan["grey"].shape)},
        "manifest": {"path": str(MANIFEST_PATH), "jobid": manifest["jobid"],
                     "seed": manifest["seed"],
                     "ps_sha256": manifest["ps_sha256"]},
        "gates": {"registration_rms_dots": rms,
                  "registration_ok": bool(reg_ok),
                  "null_tol": NULL_TOL,
                  "params": {
                      "screen_strong_db": SCREEN_STRONG_DB,
                      "screen_coherent_db": SCREEN_COHERENT_DB,
                      "knockout_miss_gate": KNOCKOUT_MISS_GATE,
                      "knockout_miss_ratio": KNOCKOUT_MISS_RATIO,
                      "presence_knockout_max": PRESENCE_KNOCKOUT_MAX,
                      "presence_preserved_min": PRESENCE_PRESERVED_MIN,
                      "ber_gate_abs": BER_GATE_ABS}},
        "gt_identity_P0_P3": ident,
        "registration": reg,
        "screen_family_fingerprints_cyc_per_dot": SCREEN_FAMILIES,
        "xcheck_002_0": XCHECK_002_0,
        "quiet_zone_control": qz,
        "screening": screening,
        "fields": fields,
        "solids": solids,
        "p4_reference_ber": p4_ber,
        "variants": variants,
        "decision": decision,
        "elapsed_s": round(time.time() - t_start, 1),
    }
    cc.save_report(report, out_path)

    # ---- human summary ----------------------------------------------------
    print("\n== VERDICT TABLE (002.1) ==")
    hdr = (f"{'variant':8s} {'screen beyond P4 bar':26s} {'solid CM (presC)':20s} "
           f"{'miss@ovl worst':14s} {'BER dC/dM/dY vs P4':20s} qualifies")
    print(hdr)
    for vid in OVERLAP_VARIANTS:
        vv = variants[vid]
        worst_miss = max((fields[nm]["split_under"]["miss_overlap"]["err"]
                          for nm in fields if nm.startswith(vid + "/")
                          and "split_under" in fields[nm]), default=float("nan"))
        dd = vv["ber_delta_vs_P4"]
        by_plane = {p: max(d for nm, d in dd.items()
                           if fields[nm]["plane"] == p)
                    for p in {fields[nm]["plane"] for nm in dd}}
        dstr = "/".join(f"{by_plane.get(p, float('nan')):+.3f}" for p in "CMY"
                        if p in by_plane)
        scr = (",".join(f.replace("lpi_pm", "@").replace("lpi_", "@")
                        for f in vv["screened_beyond_P4"]) or "clean")
        print(f"{vid:8s} {scr:26s} "
              f"{solids[vid]['solid_verdict'][:14]:16s}"
              f"({solids[vid]['presence_C_under_M']:+.2f}) "
              f"{worst_miss:14.3f} {dstr:20s} {vv['qualifies']}")
    print(f"P4 refs: BER C={p4_ber['C']:.4f} M={p4_ber['M']:.4f} "
          f"Y={p4_ber['Y']:.4f}")
    print(f"decision: adopted={decision['adopted']}  "
          f"P0 positive control screened={p0_screened}  "
          f"null failures={null_failures or 'none'}")
    if "note" in decision:
        print(f"NOTE: {decision['note']}")
    print(f"report -> {out_path}  ({report['elapsed_s']:.0f} s)")
    return report


def xcheck_calpage(scan_path: Path) -> None:
    """Regenerate the XCHECK_002_0 reference block: the identical family
    statistic on the 002.0 CAL-1 color scan (calpage manifest)."""
    scan = cc.load_scan(scan_path)
    cc.register(scan)  # default calpage manifest
    print(f"registered {scan_path}: rms "
          f"{scan['registration']['residual_rms_dots']:.2f} dots")
    for name in ("C/encode_c3", "M/encode_c3", "Y/encode_c3", "Y_encode_c3",
                 "composite_c3_C", "composite_c3_M", "composite_c3_Y"):
        v = cc.patch_view(scan, name)
        exc_p, fx, fy = _excess_db(v.crop())
        gt = cc.load_gt(v.entry)
        gt_raster = np.kron((1.0 - gt).astype(np.float32) * 255.0,
                            np.ones((v.sub, v.sub), np.float32))
        exc_g, _, _ = _excess_db(gt_raster)
        line = " ".join(
            f"{fam}={disk_excess(exc_p, fx, fy, f):5.1f}"
            f"(gt {disk_excess(exc_g, fx, fy, f):4.1f})"
            for fam, f in SCREEN_FAMILIES.items())
        print(f"{name:16s} ch={v.reg_channel} {line}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="002.1 composite probe analyzer")
    ap.add_argument("scan")
    ap.add_argument("--out", default=str(cc.BUILD / "composite_probe_report.json"))
    ap.add_argument("--xcheck-calpage", action="store_true",
                    help="instead: recompute the XCHECK_002_0 reference "
                         "numbers on the given (002.0 CAL-1 color) scan")
    args = ap.parse_args()
    if args.xcheck_calpage:
        xcheck_calpage(Path(args.scan))
    else:
        analyze(Path(args.scan), Path(args.out))

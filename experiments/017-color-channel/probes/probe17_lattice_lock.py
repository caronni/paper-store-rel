"""P2-lattice-lock-on-screen: does the blind LUMA lattice/pitch lock survive
the composite screen?

Runs the ACTUAL Stage-0 machinery (paperholo.scannorm.measure_cell_pitch =
acquire-v2 wide-band front end; paperholo.acquire.lock_grid = Stage 0) on
luma reductions of real scans, composite regions vs K-only controls:

  e004-home    finalists.png              M281 print, home flatbed 1200 dpi
               A3 = 7-state c3 composite (165-lpi off-lattice screen)
               A4 = {7+K} c4 composite; B1 = clean-K c2 control
  e004-xerox   xerox-e004-finalists-hp-scan.png   AltaLink print, home 1200
               (200-lpi 0deg grid-locked texture on composites)
  loopc-home   006col-scan-2-col.png      LOOP-C 7st-c3 composite bands
  loopbw-home  006bw-scan-1-color.png     LOOP-BW clean-K bands (c2 control)
  loopc-xerox  xerox-loop-c-hp-scan.png   AltaLink LOOP-C, home 1200
  loopbw-xerox xerox-loop-bw-hp-scan.png  AltaLink LOOP-BW (grey scan)
  office-scanner  e006bw-xeroxscan-col.png + disc1p1-xeroxscan-col.png
               AltaLink SCANNER color path at 600 dpi (secondary footing)

Ground truth geometry ONLY via the sha-gated build manifests + cal_core
registration (never re-derived).  Per crop reports:
  * measure_cell_pitch: chosen fundamental, contrast, all credible lines
  * narrow-band line probes (search_octaves=0.12) at the cell nominal and
    the known screen periods (165 lpi = 7.273 px, 224 lpi = 5.357 px,
    306 lpi = 3.922 px at 1200 dpi) -> per-line contrast + angle
  * lock_grid at the class nominal: pitch_v/u, angle, quality mean/p10
  * band phase-diff coherence at the locked pitch (trackability metric)
  * expected pitch from the registration affine (GT: cell_dots * px/dot)

Usage: env/bin/python experiments/017-color-channel/probes/probe17_lattice_lock.py \\
           --scan-dir <evidence>/scans --e004-build <gen_e004's build> \\
           --e006-build <gen_e006's build> <case> [...]
       cases: e004-home e004-xerox loopc-home loopbw-home loopc-xerox
              loopbw-xerox office-scanner all
Writes experiments/017-color-channel/build/probe17_out/<case>.json (the
record of the run is probe17_out/ beside this file).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
for rel in ("experiments/002-calibration-page",):
    sys.path.insert(0, str(ROOT / rel))

import cal_core as cc                              # noqa: E402
from paperholo import acquire as acq              # noqa: E402
from paperholo.scannorm import measure_cell_pitch, ScanRefused  # noqa: E402
from paperholo.sync import estimate_lattice       # noqa: E402

SCANS = Path()                                     # set from --scan-dir
OUT = ROOT / "experiments/017-color-channel/build/probe17_out"
DPD = 600 / 25.4                                   # layout dots per mm

# screen-period line probes, px at 1200 dpi scan (halve for 600 dpi scans)
LINES_1200 = {"165lpi": 1200 / 165.0,   # M281 composite screen  = 7.273 px
              "224lpi": 1200 / 224.0,   # M281 Y imagemask texture= 5.357 px
              "306lpi": 1200 / 306.0}   # AltaLink y-banding      = 3.922 px


def luma_from_channels(scan: dict, y0: int, y1: int, x0: int, x1: int
                       ) -> np.ndarray:
    """Scannorm-convention K reduction (mean of R,G,B / 255) of a crop of a
    registered cal_core scan; grey scans pass through /255."""
    ch = scan["channels"]
    if "r" in ch:
        crop = (ch["r"][y0:y1, x0:x1].astype(np.float64)
                + ch["g"][y0:y1, x0:x1] + ch["b"][y0:y1, x0:x1]) / 3.0
    else:
        crop = ch["grey"][y0:y1, x0:x1].astype(np.float64)
    return crop / 255.0


def probe_crop(luma: np.ndarray, cell_px_nominal: float,
               extra_lines: dict[str, float]) -> dict:
    """All Stage-0 measurements on one luma crop."""
    out: dict = {"shape": list(luma.shape)}
    # 1. acquire-v2 blind wide-band pitch identification
    t0 = time.time()
    try:
        pm = measure_cell_pitch(luma)
        out["mcp"] = {"pitch_px": pm.pitch_px, "contrast": pm.contrast,
                      "angle_deg": float(np.degrees(pm.angle_rad)),
                      "strong": [[round(p, 3), round(c, 1)]
                                 for p, c in pm.strong],
                      "candidates": [[round(p, 3), round(c, 1)]
                                     for p, c in pm.candidates]}
    except ScanRefused as e:
        out["mcp"] = {"refused": str(e)}
    # 2. narrow-band line probes (cell nominal + screen periods).
    # cell_tight (+-3.5%) separates the true cell line from the ~5.68 px
    # scanner-comb harmonic that sits inside the +-8.7% band at c3.
    probes = {"cell": (cell_px_nominal, 0.12),
              "cell_tight": (cell_px_nominal, 0.05),
              "comb11": (11.36, 0.05),
              **{k: (v, 0.12) for k, v in extra_lines.items()}}
    lines = {}
    for name, (p, oct_) in probes.items():
        if min(luma.shape) < 8 * p:
            continue
        try:
            est = estimate_lattice(luma, pitch_px_nominal=p,
                                   search_octaves=oct_)
            lines[name] = {"probe_px": round(p, 3),
                           "pitch_px": round(float(est["pitch_px"]), 4),
                           "contrast": round(float(est["contrast"]), 1),
                           "angle_deg": round(float(
                               np.degrees(est["angle_rad"])), 2)}
        except Exception as e:
            lines[name] = {"probe_px": round(p, 3), "error": str(e)}
    out["lines"] = lines
    # 3. Stage-0 lock_grid at the class nominal (unmodified receiver path)
    try:
        gm = acq.lock_grid(luma, cell_px_nominal=cell_px_nominal)
        q = np.asarray(gm.quality, np.float64).ravel()
        out["lock"] = {"pitch_v_px": float(gm.pitch_v_px),
                       "pitch_u_px": float(gm.pitch_u_px),
                       "angle_deg": float(np.degrees(gm.angle_rad)),
                       "quality_mean": float(q.mean()),
                       "quality_p10": float(np.percentile(q, 10)),
                       "quality_p50": float(np.percentile(q, 50))}
        # 4. band phase-diff coherence at the locked pitch (both widths)
        arr = acq._normalize_refl(luma)
        g = acq._grad_mag(arr)
        coh = {}
        for band in (48, 96):
            Fv, Fu, _, _ = acq._strip_phasors(
                g, gm.angle_rad, gm.pitch_v_px, gm.pitch_u_px, band, band)
            coh[f"v{band}"] = round(acq._diff_coherence(Fv, gm.pitch_v_px), 3)
            coh[f"u{band}"] = round(acq._diff_coherence(Fu, gm.pitch_u_px), 3)
        out["coherence"] = coh
    except Exception as e:
        out["lock"] = {"error": f"{type(e).__name__}: {e}"}
    out["seconds"] = round(time.time() - t0, 1)
    return out


# ---------------------------------------------------------------------------
# e004 checkerboard cases (registered tile crops)
# ---------------------------------------------------------------------------

E004_MANIFEST = Path()                             # set from --e004-build
CLASS_CELL = {"A3": 3, "A4": 4, "B1": 2}           # B2 = dot-level, skipped
INSET_MM = 1.8                                     # dodge tile edges/labels


def run_e004(scan_path: Path, n_per_class: dict[str, int],
             scale: float) -> dict:
    manifest = json.load(open(E004_MANIFEST))
    scan = cc.load_scan(scan_path)
    reg = cc.register(scan, manifest)
    st = cc.affine_stats(scan["affine"])
    res: dict = {"scan": scan_path.name, "sha256": scan["sha256"],
                 "affine_stats": {k: round(v, 5) for k, v in st.items()
                                  if isinstance(v, float)},
                 "tiles": []}
    extra = {k: v * scale for k, v in LINES_1200.items()}
    for cls, cell_dots in CLASS_CELL.items():
        tiles = [t for t in manifest["tiles"] if t["class"] == cls]
        tiles = tiles[:n_per_class.get(cls, len(tiles))]
        nominal = cell_dots * 2.0 * scale          # 2 px/dot at 1200 dpi
        exp_v = cell_dots * st["px_per_dot_y"]
        exp_u = cell_dots * st["px_per_dot_x"]
        for t in tiles:
            x0d = (t["x_mm"] + INSET_MM) * DPD
            y0d = (t["y_mm"] + INSET_MM) * DPD
            x1d = (t["x_mm"] + 21.0 - INSET_MM) * DPD
            y1d = (t["y_mm"] + 30.0 - INSET_MM) * DPD
            corners = np.array([[x0d, y0d], [x1d, y0d],
                                [x0d, y1d], [x1d, y1d]])
            px = cc.affine_apply(scan["affine"], corners)
            x0, y0 = int(np.ceil(px[:, 0].min())), int(np.ceil(px[:, 1].min()))
            x1, y1 = int(np.floor(px[:, 0].max())), int(np.floor(px[:, 1].max()))
            luma = luma_from_channels(scan, y0, y1, x0, x1)
            r = probe_crop(luma, nominal, extra)
            r.update({"tile": t["name"], "class": cls,
                      "cell_dots": cell_dots,
                      "expected_pitch_v_px": round(exp_v, 4),
                      "expected_pitch_u_px": round(exp_u, 4)})
            res["tiles"].append(r)
            lk = r.get("lock", {})
            print(f"  {t['name']:8s} mcp="
                  f"{r['mcp'].get('pitch_px', float('nan')):7.3f}px "
                  f"c={r['mcp'].get('contrast', 0):7.1f}  "
                  f"lock v/u={lk.get('pitch_v_px', float('nan')):6.3f}/"
                  f"{lk.get('pitch_u_px', float('nan')):6.3f} "
                  f"(exp {exp_v:.3f}/{exp_u:.3f}) "
                  f"q={lk.get('quality_mean', float('nan')):.3f}", flush=True)
    res["registration_rms_px"] = reg.get("rms_px")
    return res


# ---------------------------------------------------------------------------
# loop-page cases (registered band crops)
# ---------------------------------------------------------------------------

E006C_MANIFEST = Path()                            # set from --e006-build
E006BW_MANIFEST = Path()
BAND_INSET_DOTS = 8
N_BANDS = 6                                        # spread over the page
N_XWIN = 2                                         # x windows per band
XWIN_DOTS = 1200                                   # 2400 px at 1200 dpi


def run_loop(scan_path: Path, manifest_path: Path, want_color: bool,
             scale: float) -> dict:
    manifest = json.load(open(manifest_path))
    scan = cc.load_scan(scan_path)
    # refine=False: E006 pages carry only 4 corner landmarks by design
    # (analyze_e006c convention)
    reg = cc.register(scan, manifest, refine=False)
    st = cc.affine_stats(scan["affine"])
    res: dict = {"scan": scan_path.name, "sha256": scan["sha256"],
                 "affine_stats": {k: round(v, 5) for k, v in st.items()
                                  if isinstance(v, float)},
                 "tiles": []}
    extra = {k: v * scale for k, v in LINES_1200.items()}
    if want_color:                                  # e006c 7st-c3 bands
        bands = [b for b in manifest["bands"] if b["kind"] == "state_field"]
        cell_of = {b["name"]: b["params"]["cell_dots"] for b in bands}
    else:                                           # e006bw c2 K bands
        bands = [b for b in manifest["bands"]
                 if b["kind"] == "encoding_patch"
                 and b["params"].get("cell_dots") == 2]
        cell_of = {b["name"]: 2 for b in bands}
    idx = np.linspace(0, len(bands) - 1, min(N_BANDS, len(bands)))
    bands = [bands[int(i)] for i in idx]
    for b in bands:
        cell_dots = cell_of[b["name"]]
        nominal = cell_dots * 2.0 * scale
        exp_v = cell_dots * st["px_per_dot_y"]
        exp_u = cell_dots * st["px_per_dot_x"]
        for k in range(N_XWIN):
            x0d = b["x_dots"] + BAND_INSET_DOTS + k * (
                b["w_dots"] - 2 * BAND_INSET_DOTS - XWIN_DOTS) / max(
                    1, N_XWIN - 1)
            y0d = b["y_dots"] + BAND_INSET_DOTS
            x1d = x0d + XWIN_DOTS
            y1d = b["y_dots"] + b["h_dots"] - BAND_INSET_DOTS
            corners = np.array([[x0d, y0d], [x1d, y0d],
                                [x0d, y1d], [x1d, y1d]])
            px = cc.affine_apply(scan["affine"], corners)
            x0, y0 = int(np.ceil(px[:, 0].min())), int(np.ceil(px[:, 1].min()))
            x1, y1 = int(np.floor(px[:, 0].max())), int(np.floor(px[:, 1].max()))
            luma = luma_from_channels(scan, y0, y1, x0, x1)
            r = probe_crop(luma, nominal, extra)
            r.update({"tile": f"{b['name']}#x{k}", "class": "loop",
                      "cell_dots": cell_dots,
                      "expected_pitch_v_px": round(exp_v, 4),
                      "expected_pitch_u_px": round(exp_u, 4)})
            res["tiles"].append(r)
            lk = r.get("lock", {})
            print(f"  {r['tile']:16s} mcp="
                  f"{r['mcp'].get('pitch_px', float('nan')):7.3f}px "
                  f"c={r['mcp'].get('contrast', 0):7.1f}  "
                  f"lock v/u={lk.get('pitch_v_px', float('nan')):6.3f}/"
                  f"{lk.get('pitch_u_px', float('nan')):6.3f} "
                  f"(exp {exp_v:.3f}/{exp_u:.3f}) "
                  f"q={lk.get('quality_mean', float('nan')):.3f}", flush=True)
    res["registration_rms_px"] = reg.get("rms_px")
    return res


# ---------------------------------------------------------------------------
# office-scanner 600 dpi color-path cases (central crops, no registration —
# secondary footing, documented as such)
# ---------------------------------------------------------------------------

def run_office_scanner() -> dict:
    from PIL import Image
    res: dict = {"note": "AltaLink scanner color path, 600 dpi = 1 px/dot; "
                         "c2 = 2 px/cell (below scannorm floor), c3 = 3 "
                         "px/cell (marginal). Secondary footing.",
                 "tiles": []}
    cases = [("e006bw-xeroxscan-col.png", 2, "K-only page (LOOP-BW), c2"),
             ("disc1p1-xeroxscan-col.png", 3, "disc1 p1 center (K ladder)")]
    for fname, cell_dots, desc in cases:
        img = np.asarray(Image.open(SCANS / fname).convert("RGB"))
        cy, cx = img.shape[0] // 2, img.shape[1] // 2
        crop = img[cy - 1024:cy + 1024, cx - 1024:cx + 1024]
        luma = crop.astype(np.float64).mean(axis=2) / 255.0
        nominal = cell_dots * 1.0                  # 1 px/dot at 600 dpi
        extra = {k: v * 0.5 for k, v in LINES_1200.items()}
        r = probe_crop(luma, nominal, extra)
        r.update({"tile": fname, "class": "office600", "desc": desc,
                  "cell_dots": cell_dots})
        res["tiles"].append(r)
        print(f"  {fname}: mcp={r['mcp']}", flush=True)
    return res


CASES = {
    "e004-home": lambda: run_e004(SCANS / "finalists.png",
                                  {"A3": 16, "B1": 16, "A4": 8}, 1.0),
    "e004-xerox": lambda: run_e004(SCANS / "xerox-e004-finalists-hp-scan.png",
                                   {"A3": 16, "B1": 16, "A4": 8}, 1.0),
    "loopc-home": lambda: run_loop(SCANS / "006col-scan-2-col.png",
                                   E006C_MANIFEST, True, 1.0),
    "loopbw-home": lambda: run_loop(SCANS / "006bw-scan-1-color.png",
                                    E006BW_MANIFEST, False, 1.0),
    "loopc-xerox": lambda: run_loop(SCANS / "xerox-loop-c-hp-scan.png",
                                    E006C_MANIFEST, True, 1.0),
    "loopbw-xerox": lambda: run_loop(SCANS / "xerox-loop-bw-hp-scan.png",
                                     E006BW_MANIFEST, False, 1.0),
    "office-scanner": run_office_scanner,
}


def main() -> None:
    global SCANS, E004_MANIFEST, E006C_MANIFEST, E006BW_MANIFEST
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cases", nargs="*", default=["all"])
    ap.add_argument("--scan-dir", type=Path, required=True)
    ap.add_argument("--e004-build", type=Path, required=True)
    ap.add_argument("--e006-build", type=Path, required=True)
    a = ap.parse_args()
    SCANS = a.scan_dir
    E004_MANIFEST = a.e004_build / "e004_manifest.json"
    E006C_MANIFEST = a.e006_build / "e006c_manifest.json"
    E006BW_MANIFEST = a.e006_build / "e006bw_manifest.json"
    OUT.mkdir(parents=True, exist_ok=True)
    args = a.cases
    names = list(CASES) if args == ["all"] else args
    for name in names:
        print(f"=== {name} ===", flush=True)
        t0 = time.time()
        res = CASES[name]()
        res["case"] = name
        res["elapsed_s"] = round(time.time() - t0, 1)
        with open(OUT / f"{name}.json", "w") as f:
            json.dump(res, f, indent=1)
        print(f"=== {name} done in {res['elapsed_s']}s -> "
              f"{OUT / (name + '.json')}", flush=True)


if __name__ == "__main__":
    main()

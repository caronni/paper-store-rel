# Historical record of e017 (017.4, the Canon 4800 re-anchoring), retired from scratch/ 2026-10-09;
# inputs in the evidence archive. Regenerates build/probe17_canon_{dec1200.png,overview.png,reg.json} with:
#   PYTHONPATH=src:. env/bin/python experiments/017-color-channel/probes/probe17_canon_prep.py --evidence-root DIR
"""probe17_canon_prep: 017.4 step 0 — footings + registration for the FIRST
Canon 4800 dpi RGB color scan (hp-e004 finalists, home-M281 print).

The 6.88 GB TIFF is NEVER loaded whole (memmap + strip streaming):
  1. box-decimate x4 -> 1200-dpi-equivalent RGB PNG (cal_core's native
     footing; box means are aperture-honest, scannorm._box_resample doctrine)
  2. box-decimate x16 -> coarse overview PNG (field location / orientation)
  3. cal_core.load_scan + register on the x4 PNG (machinery verbatim,
     PX_PER_DOT=2 assumptions all hold) -> affine at the decimated footing
  4. native affine = 4*coef with the +1.5 px box-phase offset
     (decimated pixel i has native center 4i + 1.5), saved to JSON.

Writes:
  build/probe17_canon_dec1200.png       (10208x14032 RGB)
  build/probe17_canon_overview.png      (x16)
  build/probe17_canon_reg.json          (orientation, affines, stats)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

REPO = Path(__file__).resolve().parents[3]
for rel in ("experiments/004-finalists-checkerboard",
            "experiments/002-calibration-page",
            "experiments/003-modulation-probes",
            "experiments/001-engine-characterization",
            "src"):
    p = str(REPO / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

SCAN_REL = "paper-store-evidence-paperholo-era/004-finalists-checkerboard/finalists/captures/finalists-canon-4800rgb.tiff"   # under --evidence-root
DEC_PNG = REPO / "experiments/017-color-channel/build" / "probe17_canon_dec1200.png"
OVW_PNG = REPO / "experiments/017-color-channel/build" / "probe17_canon_overview.png"
REG_JSON = REPO / "experiments/017-color-channel/build" / "probe17_canon_reg.json"
F = 4                       # 4800 -> 1200 dpi equivalent
Image.MAX_IMAGE_PIXELS = None


def decimate_stream(mm: np.ndarray, f: int, chunk_rows: int = 4096
                    ) -> np.ndarray:
    h, w = mm.shape[0] // f * f, mm.shape[1] // f * f
    out = np.empty((h // f, w // f, 3), np.uint8)
    for y0 in range(0, h, chunk_rows):
        y1 = min(y0 + chunk_rows, h)
        blk = np.asarray(mm[y0:y1, :w], np.float32)
        d = blk.reshape((y1 - y0) // f, f, w // f, f, 3).mean(axis=(1, 3))
        out[y0 // f:y1 // f] = np.clip(np.rint(d), 0, 255).astype(np.uint8)
        print(f"  decimated rows {y0}-{y1}", flush=True)
    return out


def _scan_tiff() -> Path:
    """The e004 Canon 4800 capture under --evidence-root (strips the flag from argv)."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import argparse
    from measure import _evidence
    ap = argparse.ArgumentParser()
    _evidence.add_argument(ap)
    a, sys.argv[1:] = ap.parse_known_args()
    scan = _evidence.resolve(a.evidence_root, tool=Path(__file__).stem) / SCAN_REL
    _evidence.need(scan, tool=Path(__file__).stem)
    return scan


def main() -> None:
    scan_tiff = _scan_tiff()
    DEC_PNG.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    mm = tifffile.memmap(scan_tiff, mode="r")
    print(f"memmap {mm.shape} {mm.dtype}", flush=True)

    if DEC_PNG.exists():
        print(f"{DEC_PNG.name} exists, skipping decimation", flush=True)
        dec = np.asarray(Image.open(DEC_PNG))
    else:
        dec = decimate_stream(mm, F)
        Image.fromarray(dec).save(DEC_PNG)
        print(f"wrote {DEC_PNG} {dec.shape} ({time.time()-t0:.0f}s)",
              flush=True)
    ov = dec[:dec.shape[0] // 4 * 4, :dec.shape[1] // 4 * 4]
    ov = ov.reshape(ov.shape[0] // 4, 4, ov.shape[1] // 4, 4, 3).mean((1, 3))
    Image.fromarray(np.clip(np.rint(ov), 0, 255).astype(np.uint8)).save(OVW_PNG)

    import analyze_e004 as ae  # noqa: E402
    import cal_core as cc      # noqa: E402
    manifest = cc.load_manifest(ae.MANIFEST_PATH)
    scan = cc.load_scan(DEC_PNG)
    reg = cc.register(scan, manifest)
    st = cc.affine_stats(scan["affine"])
    coef = np.asarray(scan["affine"], np.float64)
    # native affine: dots -> native px. decimated px i covers native
    # [F*i, F*i+F-1], center F*i + (F-1)/2
    coef_native = coef * F
    coef_native[2] += (F - 1) / 2
    coef_native[5] += (F - 1) / 2
    out = {
        "scan_tiff": str(scan_tiff),
        "tiff_shape": list(mm.shape),
        "decimation_factor": F,
        "orientation": reg["orientation"],
        "affine_dec1200": [float(v) for v in coef],
        "affine_native4800": [float(v) for v in coef_native],
        "affine_stats_dec": {k: v for k, v in st.items()},
        "n_landmarks_used": reg["n_landmarks_used"],
        "n_landmarks_total": reg["n_landmarks_total"],
        "residual_rms_dots": reg["residual_rms_dots"],
        "residual_max_dots": reg["residual_max_dots"],
        "ruler_check": reg["ruler_check"],
        "inward_diagonals_match": reg["inward_diagonals_match"],
    }
    REG_JSON.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in
                      ("orientation", "affine_stats_dec", "n_landmarks_used",
                       "residual_rms_dots", "residual_max_dots",
                       "ruler_check")}, indent=1), flush=True)
    print(f"native px/dot: x {coef_native[0]:.5f}, y {coef_native[4]:.5f}")
    print(f"done in {time.time()-t0:.0f}s -> {REG_JSON}", flush=True)


if __name__ == "__main__":
    main()

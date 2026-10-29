# Historical record of e017 (017.4, the Canon 4800 re-anchoring), retired from scratch/ 2026-10-09;
# inputs in the evidence archive. Regenerates build/probe17_out/canon-artifacts.json with:
#   PYTHONPATH=src:. env/bin/python experiments/017-color-channel/probes/probe17_canon_artifacts.py --evidence-root DIR   (after probe17_canon_prep.py)
"""probe17_canon_artifacts: 017.4 instrument characterization in passing —
periodic artifacts in the Canon COLOR path (the home flatbed color mode lays
an 11.3 px comb; Canon grey had none known; Canon color = first data).

Welch-averaged periodograms of long strip profiles, per RGB channel:
  * blank LEFT margin strip  -> y-profile (transport axis periodics)
  * blank TOP margin strip   -> x-profile (CCD axis periodics)
  * in-field strip (tile column 3) -> y-profile + x-profile, with known
    content families annotated (cell 24.02 px, dot 8.008 px, M281 165 lpi
    screen 29.09 px + harmonics)

Peaks reported as (period_px, contrast = power / local-median-baseline);
contrast > 8 listed. Crops from the memmap only.

Writes experiments/017-color-channel/build/probe17_out/canon-artifacts.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import tifffile
from scipy.ndimage import median_filter
from scipy.signal import get_window

REPO = Path(__file__).resolve().parents[3]
SCAN_REL = "paper-store-evidence-paperholo-era/004-finalists-checkerboard/finalists/captures/finalists-canon-4800rgb.tiff"   # under --evidence-root
REG = json.loads((REPO / "experiments/017-color-channel/build" / "probe17_canon_reg.json").read_text())
OUT = REPO / "experiments/017-color-channel/build" / "probe17_out"
COEF = np.asarray(REG["affine_native4800"], np.float64)
DPD = 600 / 25.4

KNOWN = {"cell": 24.02, "cell/2": 12.01, "cell/3(dot)": 8.008,
         "cell/4": 6.01, "dot/2": 4.004, "screen165": 29.09,
         "screen165/2": 14.55, "screen165/3": 9.70,
         "cell_diag": 24.02 / np.sqrt(2), "screen_diag": 29.09 / np.sqrt(2)}


def dots_to_px_bbox(x0d, y0d, x1d, y1d):
    a, b, c, d, e, f = COEF
    xs = [a * x + b * y + c for x in (x0d, x1d) for y in (y0d, y1d)]
    ys = [d * x + e * y + f for x in (x0d, x1d) for y in (y0d, y1d)]
    return (int(np.ceil(min(xs))), int(np.ceil(min(ys))),
            int(np.floor(max(xs))), int(np.floor(max(ys))))


def welch_peaks(profile: np.ndarray, seg: int = 16384,
                min_period: float = 2.5, max_period: float = 4000.0,
                min_contrast: float = 8.0) -> list[dict]:
    p = profile - median_filter(profile, size=801, mode="nearest")
    n = (len(p) - seg // 2) // (seg // 2)
    if n < 1:
        seg = 1 << int(np.log2(len(p)))
        n = 1
    w = get_window("hann", seg)
    acc = np.zeros(seg // 2 + 1)
    for i in range(n):
        s = p[i * seg // 2: i * seg // 2 + seg]
        if len(s) < seg:
            break
        acc += np.abs(np.fft.rfft(s * w)) ** 2
    freqs = np.fft.rfftfreq(seg)
    base = median_filter(acc, size=101, mode="nearest")
    contrast = acc / np.maximum(base, 1e-12)
    peaks = []
    for i in range(2, len(acc) - 1):
        if freqs[i] <= 0:
            continue
        period = 1.0 / freqs[i]
        if not (min_period <= period <= max_period):
            continue
        if contrast[i] >= min_contrast and acc[i] >= acc[i - 1] \
                and acc[i] >= acc[i + 1]:
            peaks.append({"period_px": round(period, 3),
                          "contrast": round(float(contrast[i]), 1)})
    peaks.sort(key=lambda r: -r["contrast"])
    # dedupe near-identical periods
    ded = []
    for pk in peaks:
        if all(abs(pk["period_px"] / d["period_px"] - 1) > 0.03 for d in ded):
            ded.append(pk)
    return ded[:12]


def annotate(peaks: list[dict]) -> list[dict]:
    for pk in peaks:
        fam = [k for k, v in KNOWN.items()
               if abs(pk["period_px"] / v - 1.0) < 0.025]
        if fam:
            pk["family"] = "|".join(fam)
    return peaks


def strip_profiles(mm, bbox, axis: str) -> dict[str, np.ndarray]:
    x0, y0, x1, y1 = bbox
    out = {}
    blk = np.asarray(mm[y0:y1, x0:x1], np.float32)
    for i, ch in enumerate("rgb"):
        c = blk[..., i]
        out[ch] = c.mean(axis=1) if axis == "y" else c.mean(axis=0)
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
    OUT.mkdir(parents=True, exist_ok=True)
    mm = tifffile.memmap(scan_tiff, mode="r")
    res: dict = {"probe": "canon-color-path-artifacts", "strips": {}}
    strips = {
        # blank margins (content bounds 6..204 x 6..291 mm)
        "margin_left_yprofile": (dots_to_px_bbox(30, 500, 115, 6700), "y"),
        "margin_top_xprofile": (dots_to_px_bbox(420, 30, 4540, 115), "x"),
        # in-field strips: tile column 3 (x 82.5-103.5mm), rows 0-7
        "field_col3_yprofile": (dots_to_px_bbox(82.5 * DPD + 60,
                                                20.0 * DPD + 30,
                                                103.5 * DPD - 60,
                                                277.5 * DPD - 30), "y"),
        # in-field x-profile across one full tile row (y inside row 0 tiles)
        "field_row0_xprofile": (dots_to_px_bbox(12.0 * DPD + 30,
                                                21.0 * DPD,
                                                200.0 * DPD - 30,
                                                29.0 * DPD), "x"),
    }
    for name, (bbox, axis) in strips.items():
        profs = strip_profiles(mm, bbox, axis)
        rec = {"bbox_px": list(bbox), "axis": axis, "channels": {}}
        for ch, prof in profs.items():
            pk = annotate(welch_peaks(prof))
            rec["channels"][ch] = pk
            top = ", ".join(f"{p['period_px']}px x{p['contrast']}"
                            f"{'[' + p['family'] + ']' if 'family' in p else ''}"
                            for p in pk[:6])
            print(f"{name} [{ch}]: {top or 'no peaks >8x'}", flush=True)
    # also: luma of the blank margin (combined-channel comb check)
        res["strips"][name] = rec
    (OUT / "canon-artifacts.json").write_text(json.dumps(res, indent=1))
    print(f"-> {OUT / 'canon-artifacts.json'}", flush=True)


if __name__ == "__main__":
    main()

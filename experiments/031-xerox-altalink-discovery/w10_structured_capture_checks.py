"""W10 threshold derivation: comb and overshoot on the real captures.

Read-only.  Run from the repo root:
    PYTHONPATH=src env/bin/python \\
        experiments/031-xerox-altalink-discovery/w10_structured_capture_checks.py

Derives/validates the two W10 constants against real captures plus synthetic
degraded controls:

  SCANNER_COMB_MAX      — blockiness_comb max on clean blank patches must sit
                          well below it; JPEG controls (any phase, any
                          internal resolution) well above it.
  SCANNER_OVERSHOOT_MAX — slanted-edge overshoot on the two real B/W sheets
                          must sit well below it; an unsharp-masked variant
                          of the SAME real crop well above it.
"""
import io
import json
import sys

import numpy as np
import tifffile
from PIL import Image
from scipy import ndimage

sys.path.insert(0, "src")
from holo.characterize.diagnostics import (  # noqa: E402
    blockiness_comb, slanted_edge_mtf50,
)
from holo.characterize.layout import build_page  # noqa: E402

ROOT = "<repo>/"
CAPS = [
    ("xerox disc B/W", ROOT + "scratch/in/xerox-canon-cal-bw.tiff",
     4800, False),
    ("xerox disc clr", ROOT + "scratch/in/xerox-canon-cal-color.tiff",
     4800, True),
    ("m281 disc B/W",
     ROOT + "scratch/e028/e028-m281-20260804-bw-01-canon-4800gray.tiff",
     4800, False),
    ("xerox c3 2400", ROOT + "scratch/in/xerox-canon-c3-cmy7-2400dpi.tiff",
     2400, True),
]
BW_REPORTS = {
    "xerox disc B/W": ROOT + "scratch/e031/reports-w8/"
    "hcal-report-discovery-bw-copy0000-c4fd8826a63743f7.json",
    "m281 disc B/W": ROOT + "scratch/e028/reports-v4/"
    "hcal-report-discovery-bw-copy0000-76d0b6b1161c234e.json",
}


def blank_patches(path, dpi, color, count=6, patch_mm=6.0):
    """Blank-margin patches INSIDE the sheet, emulating the quiet-zone probe.

    Patch hygiene matters: a first version of this harness let patches span
    the sheet edge and platen backing (bright, smooth => high blankness
    score) and read comb 2.2-2.5 on the 2400-dpi capture; genuinely blank
    margins on the same capture read 1.0-1.08.  The analyzer's own quiet
    zone is an authored region and never has this problem — the harness must
    match that, so: stay inside ~A4 width minus margin, and reject patches
    with paper-implausible spread (std >= 10 counts = structure, not paper).
    """
    array = tifffile.memmap(path)
    px = int(patch_mm / 25.4 * dpi)
    height = array.shape[0]
    sheet_width = int(210.0 / 25.4 * dpi)          # A4 columns in this scan
    x_hi = min(array.shape[1], sheet_width - int(3.0 / 25.4 * dpi)) - px
    x_lo = sheet_width - int(9.0 / 25.4 * dpi)     # the outer margin band
    scored = []
    for y in range(int(height * 0.15), int(height * 0.85), px * 2):
        for x in range(x_lo, x_hi, max(px // 2, 1)):
            tile = np.asarray(array[y:y + px, x:x + px], np.float64)
            if tile.shape[0] < px or tile.shape[1] < px:
                continue
            grey = tile.mean(axis=2) if color else tile
            if grey.std() >= 10.0:
                continue
            scored.append((grey.mean() - 3.0 * grey.std(), grey))
    scored.sort(key=lambda item: -item[0])
    return [grey for _score, grey in scored[:count]]


def jpeg(image, quality):
    buffer = io.BytesIO()
    Image.fromarray(np.clip(image, 0, 255).astype(np.uint8)).save(
        buffer, "JPEG", quality=quality
    )
    return np.asarray(Image.open(io.BytesIO(buffer.getvalue())), np.float64)


print("=== comb: clean blank patches (max over periods 8..64) ===")
worst_clean = 0.0
reference_patch = None
for name, path, dpi, color in CAPS:
    values = []
    for grey in blank_patches(path, dpi, color):
        if reference_patch is None:
            reference_patch = grey
        comb = blockiness_comb(grey)
        if comb is not None:
            values.append(comb["max"])
    worst_clean = max(worst_clean, max(values))
    print(f"  {name:<16} n={len(values)}  median {np.median(values):.3f}  "
          f"max {max(values):.3f}")
print(f"  worst clean comb max: {worst_clean:.3f}")

print("\n=== comb: degraded controls on a real patch ===")
patch = reference_patch
controls = [
    ("JPEG q75 @ delivered, phase 3px", jpeg(patch, 75)[3:-5, 3:-5]),
    ("JPEG q50 @ delivered", jpeg(patch, 50)),
]
half = patch[::2, ::2]
up = np.asarray(Image.fromarray(
    np.clip(jpeg(half, 60), 0, 255).astype(np.uint8)
).resize(patch.shape[::-1], Image.BILINEAR), np.float64)
controls.append(("JPEG q60 @ half-res, bilinear up", up[5:, 2:]))
weakest_control = float("inf")
for label, degraded in controls:
    comb = blockiness_comb(degraded)
    weakest_control = min(weakest_control, comb["max"])
    print(f"  {label:<34} max {comb['max']:.3f} @ {comb['max_period_px']}px")
print(f"  weakest degraded control: {weakest_control:.3f}")

print("\n=== overshoot: real slanted-edge crops ===")
page = build_page(stage="discovery", kind="bw", copy_index=0, request_code=0)
probe = next(row for row in page["probes"] if row["kind"] == "slanted_edge")
angle = float(probe["params"]["angle_deg"])
worst_real = 0.0
weakest_sharpened = float("inf")
for name, report_path in BW_REPORTS.items():
    report = json.load(open(report_path))
    coef = np.asarray(report["geometry"]["affine_layout_to_scan"])
    x0, y0 = float(probe["x_layout_dots"]), float(probe["y_layout_dots"])
    w, h = float(probe["w_layout_dots"]), float(probe["h_layout_dots"])
    corners = np.asarray([[x0, y0], [x0 + w, y0], [x0 + w, y0 + h],
                          [x0, y0 + h]])
    scan = corners @ coef[:, :2].T + coef[:, 2]
    sx0, sy0 = (int(scan[:, 0].min()) + 8, int(scan[:, 1].min()) + 8)
    sx1, sy1 = (int(scan[:, 0].max()) - 8, int(scan[:, 1].max()) - 8)
    array = tifffile.memmap(
        CAPS[0][1] if name.startswith("xerox") else CAPS[2][1])
    crop = np.asarray(array[sy0:sy1, sx0:sx1], np.float64) / 255.0
    rotation = float(report["geometry"]["rotation_deg"])
    clean = slanted_edge_mtf50(crop, 4800.0, 4800.0, angle + rotation)
    # Control at half the measured edge width (mtf50 ~4.1 c/mm => 10-90
    # width ~53 px; sweep on the real crop with the envelope-referenced
    # metric: sigma 12/24/48/96 at amount 1.0 -> overshoot 0.0005/0.0996/
    # 0.1998/0.2878).  Sub-edge-width radii are
    # near-invisible AND near-harmless at this footing — nothing at those
    # frequencies survives the optics — so the detector responds in
    # proportion to a sharpener's capacity to distort, which is the
    # property a gate wants.  sigma 24 is the weakest harmful-class control.
    sharpened_crop = crop + 1.0 * (crop - ndimage.gaussian_filter(crop, 24.0))
    sharpened = slanted_edge_mtf50(
        sharpened_crop, 4800.0, 4800.0, angle + rotation)
    worst_real = max(worst_real, clean["overshoot_fraction"])
    weakest_sharpened = min(
        weakest_sharpened, sharpened["overshoot_fraction"])
    print(f"  {name:<16} clean overshoot {clean['overshoot_fraction']:.4f} "
          f"(mtf50 {clean.get('mtf50_cycles_per_mm', 0):.1f} c/mm)  |  "
          f"unsharp-masked {sharpened['overshoot_fraction']:.4f}")
print(f"  worst real overshoot: {worst_real:.4f}   "
      f"weakest sharpened control: {weakest_sharpened:.4f}")

print("\n=== verdict vs the shipped constants ===")
from holo.characterize.summarize_physical import (  # noqa: E402
    SCANNER_COMB_MAX, SCANNER_OVERSHOOT_MAX,
)
comb_ok = worst_clean < SCANNER_COMB_MAX < weakest_control
edge_ok = worst_real < SCANNER_OVERSHOOT_MAX < weakest_sharpened
print(f"  comb: clean {worst_clean:.3f} < {SCANNER_COMB_MAX} < "
      f"controls {weakest_control:.3f}  ->  {'OK' if comb_ok else 'FAIL'}")
print(f"  overshoot: real {worst_real:.4f} < {SCANNER_OVERSHOOT_MAX} < "
      f"sharpened {weakest_sharpened:.4f}  ->  {'OK' if edge_ok else 'FAIL'}")
sys.exit(0 if comb_ok and edge_ok else 1)

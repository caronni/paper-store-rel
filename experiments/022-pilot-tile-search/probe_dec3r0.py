#!/usr/bin/env python
# Historical record of e022 (the decimated-3 region-0 mechanism probe, DESIGN-NOTES), retired from scratch/
# 2026-10-09; inputs in the evidence archive. Regenerates the probe's numbers (stdout) with:
#   PYTHONPATH=src:. env/bin/python experiments/022-pilot-tile-search/probe_dec3r0.py --evidence-root DIR
"""Probe: why does the v1 e022 leave decimated-3 region 0 unresolved?

Measures, for the largest region of decimated-3_1600.tiff:
- the e021 angle hint;
- segment.lattice_angle on the block-mean work image (v1's fallback seed);
- the blind contrast objective over a wide angle scan;
- v1 sample_region outcome at the default +-1 deg envelope vs a wide one;
- correlation placement at the best wide-scan angle.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/022-pilot-tile-search"))

from paperholo import pilotsearch, platen, segment  # noqa: E402
import run_e022  # noqa: E402
import argparse  # noqa: E402
from measure import _evidence  # noqa: E402

_AP = argparse.ArgumentParser()
_evidence.add_argument(_AP)
EVIDENCE = _evidence.resolve(_AP.parse_args().evidence_root, tool="probe_dec3r0")

# The 1600 dpi decimation is not in the published archive (tier delete: it
# regenerates byte-identically from the published 4800 capture); it is read
# from build/, where the recipe below writes it.
SOURCE_4800 = EVIDENCE / "paper-store-evidence-paperholo-era/018-confetti-c3-play/confetti/captures/confetti-canon-4800grey-3.tiff"
DECIMATED = ROOT / "experiments/022-pilot-tile-search/build/decimated-3_1600.tiff"
_evidence.need(DECIMATED, tool="probe_dec3r0", regenerate=(
    f"env/bin/python experiments/018-confetti-c3-play/decimate_scan.py "
    f"{SOURCE_4800} {DECIMATED} --factor 3"))
img = run_e022.load_image(DECIMATED)
survey = platen.detect_payload_regions(img, dpi=1600.0)
print(f"regions={len(survey.regions)} c={survey.c_dots} "
      f"pitch={survey.cell_pitch_px}")
region = survey.regions[0]
print(f"region0 bbox={region.bbox} area={region.area_mm2:.0f}mm2 "
      f"hint={region.angle_hint_deg}")

pitch = float(survey.cell_pitch_px)
cfg = pilotsearch.SearchConfig()

# v1 default envelope
sam = pilotsearch.sample_region(img, region, 0, pitch, config=cfg)
print("v1 default sample_region:",
      "None" if sam is None else
      f"angle={sam.work_angle_deg:.3f} contrast={sam.contrast:.4f}")

# wide angle scan using the same machinery
y0, x0, h, w = region.bbox
crop = np.asarray(img[y0:y0 + h, x0:x0 + w], np.float32)
mask = np.asarray(region.mask[:crop.shape[0], :crop.shape[1]], bool)
factor = max(1, int(round(pitch / cfg.target_cell_px)))
work = pilotsearch._block_mean(crop, factor)
wmask = pilotsearch._block_mask(mask, factor)
wp = pitch / factor
la = segment.lattice_angle(work, wmask, wp)
print(f"lattice_angle(work)={la:.3f} deg")

best = None
for angle in np.arange(-45.0, 45.0, 0.5):
    got = pilotsearch.sample_region(
        img, region, 0, pitch,
        config=pilotsearch.SearchConfig(angle_offsets_deg=(0.0,)),
        angle_prior_deg=float(angle))
    if got is None:
        continue
    if best is None or got.contrast > best.contrast:
        best = got
print("wide-scan best:",
      "None" if best is None else
      f"angle={best.work_angle_deg:.3f} contrast={best.contrast:.4f}")

if best is not None:
    windows = pilotsearch.region_windows(best, cfg)
    print(f"windows={len(windows)} top support={windows[0].support}")
    win = windows[0]
    bits = best.bits[win.y:win.y + win.h, win.x:win.x + win.w]
    msk = pilotsearch._core(
        best.mask[win.y:win.y + win.h, win.x:win.x + win.w], cfg.erode_cells)
    ev = best.evidence[win.y:win.y + win.h, win.x:win.x + win.w]
    spec = run_e022.E018.spec()
    placed = pilotsearch.correlate_fragment(
        ev, msk, spec, run_e022.E018.seed, pages=(0,),
        pending_cell_mask=None, config=cfg)
    print(f"correlation at best angle: ok={placed.ok} "
          f"mismatch={placed.mismatch:.3f} rival={placed.rival_mismatch:.3f} "
          f"validation={placed.diagnostics.get('validation_mismatch')}")

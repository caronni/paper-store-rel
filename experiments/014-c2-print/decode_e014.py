#!/usr/bin/env python
# Historical record of e014 (014.2), retired from scratch/ 2026-10-09; inputs in the evidence archive.
# Regenerates the e014 blind hardware decode verdict (stdout) with:
#   PYTHONPATH=src:. env/bin/python experiments/014-c2-print/decode_e014.py --evidence-root DIR
"""Blind c2 HARDWARE decode of the e014 sheet (Xerox print, Canon 4800 gray).

The e014 receiver leg's hardware verdict. Uses the acquire-v2 blind front
end (formats.acquire_scan) with NO hints beyond the registry + trusted dpi.
Falls back to a genie-aligned cell-BER diagnostic when acquire returns
ok=False, so we learn the channel truth even if the c3-calibrated post-fold
word gate false-vetoes at c2-class BER (the queued follow-up).

GROUND-TRUTH RULE (012.3): payload_gt drawn EXACTLY as gen_e014 draws it
(dtype=np.uint8 inside integers()). Re-derive via the gen module.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
import argparse
from measure import _evidence
_AP = argparse.ArgumentParser()
_evidence.add_argument(_AP)
_AP.add_argument('--out', type=Path, default=Path(__file__).resolve().parent / 'build')
ARGS, _ = _AP.parse_known_args()
EVIDENCE = _evidence.resolve(ARGS.evidence_root, tool='decode_e014')
ARGS.out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'experiments/014-c2-print'))
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
import tifffile

from paperholo import compose, formats, scannorm, acquire
from paperholo.modulation import rng
import gen_e014

SCAN = EVIDENCE / 'paper-store-evidence-paperholo-era/014-c2-print/A/captures/A-canon-4800grey-a.tiff'
_evidence.need(SCAN, tool='decode_e014')
SEED = gen_e014.SEED
spec = gen_e014.make_spec()
CELL_DOTS = 2
SCAN_DPI = 4800.0
payload_gt = rng(SEED, b"e014/payload").integers(
    0, 2, compose.payload_capacity(spec), dtype=np.uint8)
cp = compose.compose_page(payload_gt, spec, SEED, page=0)   # GT scrambled cells
assert np.array_equal(compose.extract_payload(cp.cell_values, spec, SEED, 0),
                      payload_gt)
GTcells = cp.cell_values                                     # (3300,2220)


def genie_ber(win_scan, plane='K'):
    """Pipeline-free floor: lock at native 16 px/cell, blind-detect, best
    genie cell agreement over +-3 cell offsets, split pilot/payload."""
    img = scannorm.reduce_plane(win_scan, plane)
    grid = acquire.lock_grid(img, cell_px_nominal=16.0, cell_dots=CELL_DOTS)
    hard, _ = acquire.cell_bits_blind(
        acquire.sample_cell_means(img, grid, cell_dots=CELL_DOTS))
    H, W = hard.shape
    return grid, hard  # scoring done by caller against absolute coords


def main():
    print(f"scan: {SCAN}  ({SCAN.stat().st_size/1e9:.2f} GB)", flush=True)
    tf = tifffile.TiffFile(str(SCAN))
    p0 = tf.pages[0]
    print(f"dims {p0.shape} dtype {p0.dtype} photometric {p0.photometric}",
          flush=True)
    arr = p0.asarray(out='memmap')
    Hs, Ws = arr.shape[:2]

    # c2 @600 print, 4800 scan = 16 px/cell. A 40 mm blind window:
    cpm = 600 / 25.4 / CELL_DOTS          # cells/mm at c2 = 11.81
    for mm, (fy, fx) in [(40, (0.5, 0.5)), (40, (0.42, 0.42)),
                         (40, (0.58, 0.58)), (25, (0.5, 0.5))]:
        src = int(mm * cpm * CELL_DOTS * 8)   # px at 8 px/dot
        y0 = max(0, int(Hs * fy) - src // 2)
        x0 = max(0, int(Ws * fx) - src // 2)
        win = np.asarray(arr[y0:y0 + src, x0:x0 + src], dtype=np.float32)
        t0 = time.perf_counter()
        r = formats.acquire_scan(win, scan_dpi=SCAN_DPI)
        dt = time.perf_counter() - t0
        if r.ok:
            idx = r.result.payload_cell_index
            ber = float(np.mean(r.result.payload_bits != payload_gt[idx]))
            null = float(np.mean(r.result.payload_bits
                                 != payload_gt[(idx + 7919) % payload_gt.size]))
            print(f"{mm}mm ({fy},{fx}): BLIND OK {r.fmt.format_id} "
                  f"footing {r.norm.cell_px_est:.2f}px/cell "
                  f"BER {100*ber:.2f}% null {null:.3f} "
                  f"tiles {r.result.n_tiles_decoded}/"
                  f"{r.result.n_tiles_attempted} werr "
                  f"{r.result.n_word_errors_corrected} "
                  f"geomY={r.geometry_confirmed} {dt:.1f}s", flush=True)
        else:
            # diagnose: did the front end identify + register, and the gate veto?
            print(f"{mm}mm ({fy},{fx}): blind acquire ok=False "
                  f"stage={r.diagnostics.get('failed_stage')} "
                  f"tried={[(t[0],str(t[1])[:40]) for t in r.tried]} {dt:.1f}s",
                  flush=True)
            # genie floor at native 16 px/cell to expose the channel truth
            try:
                grid, hard = genie_ber(win)
                H, W = hard.shape
                best = (0.0, None)
                for dy in range(-3, 4):
                    for dx in range(-3, 4):
                        gy0, gx0 = max(0, dy), max(0, dx)
                        gy1 = min(GTcells.shape[0], H + dy)
                        gx1 = min(GTcells.shape[1], W + dx)
                        if gy1 - gy0 < 80 or gx1 - gx0 < 80:
                            continue
                        # try center region of the page (unknown abs origin —
                        # scan best local agreement is a lower bound)
                        sub = hard[gy0 - dy:gy1 - dy, gx0 - dx:gx1 - dx]
                        # can't align to absolute without pilots; report the
                        # blind-detect ink balance + lattice quality instead
                        best = (float(sub.mean()), (dy, dx))
                print(f"      genie floor: lattice pitch "
                      f"{float(np.mean(grid.pitch_v_px)):.3f}/"
                      f"{float(np.mean(grid.pitch_u_px)):.3f} px/cell, "
                      f"hard-bit ink fraction {hard.mean():.3f} "
                      f"(GT payload 0.50) — registration needs pilots; see "
                      f"the gate note", flush=True)
            except Exception as e:
                print(f"      genie floor failed: {type(e).__name__}: {e}",
                      flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# Historical record of e029 (generator of the printed sheet, also e032's AltaLink K reprint), retired from
# scratch/e028/holo-c2-r0700-q07-ink-counting/ 2026-10-09; the emitted volume is in the evidence archive.
# Regenerates page000.ps, page000_gt.npy, manifest.json, payload-counting.bin with: PYTHONPATH=src env/bin/python experiments/029-holo-v1-first-print/generate_e029.py
# 2026-10-12 (R21, cmy generator W2b): through the fossil L:c2-r0700@3392x2368, the printer an emission engine — the
# PS, GT and payload are the archived bytes; the manifest records the fossil's 4.0 mm and engine hp-m281 where the
# archived one records 4.5 mm and hp-m281-ink (measure/evidence_regen's e029 recipe reproduces that through --coding).
"""Emit one-page c2-r0700 q=0.7 at ink-tight geometry with counting payload.

Run from the paper repo root (needs src/ on path via PYTHONPATH=src):

  env/bin/python experiments/029-holo-v1-first-print/generate_e029.py

Or re-emit into a fresh directory (volumes refuse overwrite):

  .../generate_e029.py --out build/holo-c2-r0700-q07-ink-counting-rerun

Notes
-----
- The page is the fossil ``c2-r0700@3392x2368`` (the e028 ink-tight
  field, first derived from the 4.5 mm ``hp-m281-ink`` row; actual
  borders ~4.91/4.74 mm). Expect clipped edge tiles vs e028 clip
  ~4.15–4.28 mm; q=0.7 is the cushion.
- Payload = counting bytes 0,1,2,...,255,0,... to max_payload_bytes.
- Does NOT print. Print only via scripts/print_plane.sh after an explicit go.
- Decode: ``./confetti.py decode SCAN.tiff --scan-dpi 4800 \\
    --coding c2-r0700 --printer hp-m281-ink --state ... --out ...``
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

# Allow running without an editable install.
_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from holo.devices.registry import PRINTERS
from holo.format.fossils import resolve_fossil_spec
from holo.gen.emit import emit_volume
from holo.gen.plan import max_payload_bytes


def main() -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=here / "build" / "holo-c2-r0700-q07-ink-counting",
        help="volume output directory (default: build/holo-c2-r0700-q07-ink-counting "
             "beside this script)",
    )
    ap.add_argument(
        "--source-fraction",
        type=float,
        default=0.7,
        help="fountain source fraction q (default 0.7)",
    )
    args = ap.parse_args()

    spec = resolve_fossil_spec("c2-r0700@3392x2368")
    q = args.source_fraction
    n = max_payload_bytes(spec, q, 1)
    payload = bytes(i & 0xFF for i in range(n))

    out = args.out
    # If re-emitting into this dir and artifacts already exist, refuse
    # via emit_volume's no-overwrite rule — caller must pick --out.
    vol = emit_volume(spec, payload, q, out, printer=PRINTERS["hp-m281"])
    (out / "payload-counting.bin").write_bytes(payload)

    lay = spec.layout
    print(f"OUT {out.resolve()}")
    print(f"payload_bytes {n}")
    print(f"payload_sha256 {hashlib.sha256(payload).hexdigest()}")
    print(f"spec_id {spec.spec_id}")
    print(
        f"pages {vol.plan.n_pages} K {vol.plan.k_total} "
        f"N {vol.plan.n_symbols_total} repair {vol.plan.n_repair}"
    )
    print(f"cells {lay.cells_yx} tiles/page {lay.tiles_per_page}")
    print(
        "borders_mm t/b/l/r "
        f"{lay.border_top_mm:.3f}/{lay.border_bottom_mm:.3f}/"
        f"{lay.border_left_mm:.3f}/{lay.border_right_mm:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

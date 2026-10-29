#!/usr/bin/env python3
"""Emit the 2026-08-18 Xerox AltaLink C8245 candidate set.

REQUIRES the c4/4mm/cmy8-rung patch applied (branch `c4-row`): the A sheet
needs the c4 row, every 4mm sheet needs the xerox-altalink-c8245-ink
printer row, and H/I need the CMY8 r0850/r0700 experiment rungs. On plain
main this script raises on the first unknown id -- and since 2026-10-12
(CMY-DESIGN R21, generator plan W2b) it fails at import on main, where
`make_spec` is gone: it runs only inside the bcd352c1 / f1bc0d0f trees the
evidence recipes (measure/evidence_regen, e033-original / e033-patch) copy
it into.  Kept as it was; a fossil of that branch.

One page per volume, counting payload filling the page exactly.  Does NOT
print: printing goes through scripts/print_plane.sh after an explicit go
(.claude/rules/hardware.md).

  env/bin/python experiments/033-xerox-rung-experiments/generate_set.py \\
      [--out DIR]   # default: this experiment's build/

Every volume refuses to overwrite an existing directory; re-emit into a
fresh --out.  Decode each sheet with its own --coding and --printer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from holo.devices.profiles import make_spec
from holo.gen.emit import emit_volume
from holo.gen.plan import max_payload_bytes, pooled_plane_tier

XEROX_6MM = "xerox-altalink-c8245"
XEROX_4MM = "xerox-altalink-c8245-ink"

# tag, directory, coding, printer, q
SET = (
    ("A", "A-c4-r0550-q030-6mm",       "c4-r0550",        XEROX_6MM, 0.3),
    ("A2", "A2-c3-r0550-q030-6mm",     "c3-r0550",        XEROX_6MM, 0.3),
    ("B", "B-c2-r0700-q070-4mm",       "c2-r0700",        XEROX_4MM, 0.7),
    ("C", "C-c2-r0700-q090-4mm",       "c2-r0700",        XEROX_4MM, 0.9),
    ("D", "D-c2-cmy8v1-q050-4mm",      "c2-cmy8-p120-v1", XEROX_4MM, 0.5),
    ("E", "E-c2-cmy8v1-q090-4mm",      "c2-cmy8-p120-v1", XEROX_4MM, 0.9),
    ("F", "F-c3-cmy8v1-q090-4mm",      "c3-cmy8-p120-v1", XEROX_4MM, 0.9),
    ("G", "G-c3-r0550-q090-4mm",       "c3-r0550",        XEROX_4MM, 0.9),
    # Experiment rungs: pooled CMY8 at a higher per-plane LDPC rung, the
    # thing holo3's `max` profile has and the -v1 rows did not.
    ("H", "H-c2-cmy8r0850-q090-4mm", "c2-cmy8-r0850-p120-x1", XEROX_4MM, 0.9),
    ("I", "I-c2-cmy8r0700-q090-4mm", "c2-cmy8-r0700-p120-x1", XEROX_4MM, 0.9),
)


def main() -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=here / "build",
                    help="root directory for the volume subdirectories")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rows = []
    for tag, dirname, coding, printer, q in SET:
        spec = make_spec(coding, printer)
        n = max_payload_bytes(spec, q, 1)
        payload = bytes(i & 0xFF for i in range(n))
        out = args.out / dirname
        vol = emit_volume(spec, payload, q, out,
                          profile=None, printer_id=printer)
        (out / "payload-counting.bin").write_bytes(payload)
        lay = spec.layout
        ps = out / "page000.ps"
        rows.append({
            "tag": tag,
            "dir": dirname,
            "coding": coding,
            "printer": printer,
            "margin_mm": spec.margin_mm,
            "spec_id": spec.spec_id,
            "cell_dots": spec.coding.cell_dots,
            "planes": "K" if "cmy" not in coding else "CMY",
            "field_cells": f"{lay.cells_yx[0]}x{lay.cells_yx[1]}",
            "tiles_per_page": lay.tiles_per_page,
            "borders_mm_tblr": [round(lay.border_top_mm, 2),
                                round(lay.border_bottom_mm, 2),
                                round(lay.border_left_mm, 2),
                                round(lay.border_right_mm, 2)],
            "q_dial": q,
            "payload_bytes": n,
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "k_total": vol.plan.k_total,
            "n_symbols_total": vol.plan.n_symbols_total,
            "effective_k_over_n": round(vol.plan.effective_k_over_n, 6),
            "net_bits_per_mm2": round(vol.plan.net_bits_per_mm2, 2),
            "plane_tier": pooled_plane_tier(spec, q),
            "ps_bytes": ps.stat().st_size,
            "ps_sha256": hashlib.sha256(ps.read_bytes()).hexdigest(),
        })
        print(f"{tag}  {spec.spec_id:28s} q={q}  "
              f"{n:>9,} B  tiles {lay.tiles_per_page}")

    (args.out / "set.json").write_text(json.dumps(rows, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

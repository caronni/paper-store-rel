#!/usr/bin/env python3
"""e014 — ARCH-2: the c2 archive-style pilot sheet (layout_version 3).

Same v3 format machinery as e012 (p60b6.v3 pilots, 18-bit flat counter in
BCH(100,23) words, no overt furniture), at kcell-c2: cell = 2x2 dots
(300 cpi), page 3300x2220 cells = 6600x4440 dots on A4, 55x37 = 2035 word
tiles, payload capacity 7,122,500 bits (random, scrambled).

ENCODE-SIDE ONLY by explicit user decision (2026-07-08): the blind
receiver's c2-class machinery (ctx-detected pilot bits, duplicated words —
PILOTS-DESIGN section 6.2) is unbuilt; this sheet exists so real c2+pilot
hardware scans are in hand when that work lands. Channel expectations at
c2: 11-14% hard BER (measured, both engines), day-fragile 2-dot whites.

Deterministic + sha-gated; preflight tests/test_e014.py (incl. gs
pixel-exact render + golden sha).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np

from paperholo.compose import (ComposeSpec, compose_page, emit_composed,
                               payload_capacity)
from paperholo.modulation import rng
from paperholo.pilots import PilotLayout

SEED = b"paper-store/exp014-c2"
OUT = Path(__file__).resolve().parent / "build"
PS_BUDGET_BYTES = 30_000_000


def make_spec() -> ComposeSpec:
    """The frozen e014 page spec: kcell-c2, v3 words, 6mm+ margins.

    3300x2220 cells (multiples of P=60) = 6600x4440 dots at (260, 208) on
    A4 4960x7016 -> margins 11.0 mm (x) / 8.8 mm (y)."""
    return ComposeSpec(layout_version=3, encoding_id="kcell-c2",
                       pilot=PilotLayout(version=3),
                       page_cells_yx=(3300, 2220), x_dots=260, y_dots=208)


def main() -> int:
    t0 = time.time()
    spec = make_spec()
    payload = rng(SEED, b"e014/payload").integers(
        0, 2, size=payload_capacity(spec), dtype=np.uint8)
    composed = compose_page(payload, spec, SEED, page=0)

    OUT.mkdir(parents=True, exist_ok=True)
    mf = emit_composed(
        composed, OUT / "e014.ps",
        title="paperholo e014 c2 pilot page",
        artifact="e014",
        experiment="014-c2-print",
        print_command=("scripts/print_plane.sh "
                       "experiments/014-c2-print/build/e014.ps"),
        extra_manifest={
            "artifact": "e014",
            "run": "014.0",
            "word_provider": "pilots.encode_word",
            "decode_status": ("encode-side only: c2-class blind receiver "
                              "deferred by user decision 2026-07-08"),
        })
    assert mf["ps_bytes"] <= PS_BUDGET_BYTES, \
        f"ps {mf['ps_bytes'] / 1e6:.1f} MB > {PS_BUDGET_BYTES / 1e6:.0f} MB budget"
    ty, tx = spec.page_tiles_yx
    print(f"wrote build/e014.ps ({mf['ps_bytes'] / 1e6:.2f} MB, "
          f"{composed.payload_capacity_bits} payload bits, "
          f"{ty * tx} pilot tiles (v3 counter: tiles_x={tx}, "
          f"tiles_per_page={ty * tx}), {time.time() - t0:.1f} s)")
    print(f"sha256 {mf['ps_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

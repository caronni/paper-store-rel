#!/usr/bin/env python
"""E012 pilot hardware page: the first layout_version-3 pilot-composed sheet.

One A4 K-plane kcell-c3 field, geometry identical to e011 (2220x1500 cells =
4500x6660 dots at (230,178), >= 6 mm margins), p60b6.v3-k18 pilot lattice:
SAME site derivation as v2 (b"pilot-sites-v2" label, deliberately shared),
new VALUE layer — BCH(127,50,t=13) -> (100,23), d>=27, carrying an 18-bit
flat tile counter (c = page*925 + ty*25 + tx) + 5 zero pads, scrambled with
the b"pilot-values-v3" plane-labeled keystream. No version field, no plane
field: the scramble label IS the format identity (implicit signaling).
Payload = 3,237,500 seeded random bits, scrambled per the encodings kcell
convention. Archive-style emission: ONE whole-page imagemask, no header/
sentinel/marks (DESIGN R3).

FROZEN PAYLOAD DERIVATION (same dtype-qualified literal form as e011 —
the dtype kwarg changes NumPy's bounded-integer draw stream, keep the form):
    rng(SEED, b"e012/payload").integers(0, 2, payload_capacity(spec),
                                        dtype=np.uint8)

Outputs: build/e012.ps + build/e012_manifest.json + build/e012_gt/*.npy.
Byte-identical regeneration from SEED; sha256 gates reuse (pinned by
tests/test_format_v3_golden.py). Preflight: pytest tests/test_e012.py.
Print ONLY via scripts/print_plane.sh after user confirmation in-session
(.claude/rules/hardware.md).
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from paperholo.compose import (ComposeSpec, compose_page, emit_composed,
                               payload_capacity)
from paperholo.modulation import rng
from paperholo.pilots import PilotLayout

SEED = b"paper-store/exp012-pilot1"
OUT = Path(__file__).resolve().parent / "build"
PS_BUDGET_BYTES = 30_000_000  # repo cap (gen_e006 convention)


def make_spec() -> ComposeSpec:
    """The frozen e012 page spec: e011 geometry, layout_version 3."""
    return ComposeSpec(layout_version=3, pilot=PilotLayout(version=3))


def main() -> int:
    t0 = time.time()
    spec = make_spec()
    payload = rng(SEED, b"e012/payload").integers(
        0, 2, size=payload_capacity(spec), dtype=np.uint8)
    composed = compose_page(payload, spec, SEED, page=0)

    OUT.mkdir(parents=True, exist_ok=True)
    mf = emit_composed(
        composed, OUT / "e012.ps",
        title="paperholo e012 pilot page",
        artifact="e012",
        experiment="012-pilot-print",
        print_command=("scripts/print_plane.sh "
                       "experiments/012-pilot-print/build/e012.ps"),
        extra_manifest={
            "artifact": "e012",
            "run": "012.0",
            "word_provider": "pilots.encode_word",
        })
    assert mf["ps_bytes"] <= PS_BUDGET_BYTES, \
        f"ps {mf['ps_bytes'] / 1e6:.1f} MB > {PS_BUDGET_BYTES / 1e6:.0f} MB budget"

    ty, tx = spec.page_tiles_yx
    print(f"wrote build/e012.ps ({mf['ps_bytes'] / 1e6:.2f} MB, "
          f"{composed.payload_capacity_bits} payload bits, "
          f"{ty * tx} pilot tiles (v3 counter: tiles_x={tx}, "
          f"tiles_per_page={ty * tx}), {time.time() - t0:.1f} s)")
    print(f"sha256 {mf['ps_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""E011 pilot round-trip page: the first layout_version-2 pilot-composed sheet.

One A4 K-plane kcell-c3 field, 2220x1500 cells (4500x6660 dots at (230,178) —
>= 6 mm margins on all sides), p60b6.v2 pilot lattice (37x25 period tiles x
100 sites = 92,500 pilot cells), payload = 3,237,500 seeded random bits,
scrambled per the encodings kcell convention. Archive-style emission: ONE
whole-page imagemask, no header/sentinel/marks (DESIGN R3).

Outputs: build/e011.ps + build/e011_manifest.json + build/e011_gt/*.npy.
Byte-identical regeneration from SEED; sha256 gates reuse. Preflight:
pytest tests/test_e011.py. Print ONLY via scripts/print_plane.sh after user
confirmation in-session (.claude/rules/hardware.md).

FROZEN PAYLOAD DERIVATION (finding [4], wave-3 — declared deviation from the
wave contract's literal form): the e011 payload is EXACTLY
    rng(SEED, b"e011/payload").integers(0, 2, payload_capacity(spec),
                                        dtype=np.uint8)
The dtype=np.uint8 argument changes NumPy's bounded-integer draw stream (the
no-dtype form yields an UNCORRELATED bit sequence — agreement 0.491 measured),
so any GT regeneration for BER scoring MUST use this dtype-qualified call (or
load the persisted GT npy via cal_core.load_gt). This derivation supersedes
the contract's no-dtype literal; the layout_version-2 golden sha
(tests/test_format_v2_golden.py) pins it — do not "fix" it to match the
contract text, that would fork the frozen format.

--fake-words (DEBUG, default OFF): substitutes deterministic rng-derived pilot
words for pilots.encode_word so the composition/emission path can be exercised
before the pilot ECC lands. Fake-word pages are NOT decodable stimuli — the
manifest records word_provider and the PS title carries FAKE-WORDS; never
print one.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from paperholo.compose import (ComposeSpec, PilotLayout, _sites_per_tile,
                               compose_page, emit_composed, payload_capacity)
from paperholo.modulation import rng

SEED = b"paper-store/exp011-pilot1"
OUT = Path(__file__).resolve().parent / "build"
PS_BUDGET_BYTES = 30_000_000  # repo cap (gen_e006 convention)


def fake_word_provider(seed: bytes, layout: PilotLayout):
    """Deterministic stand-in pilot words (DEBUG only, not the pilot code)."""
    n_sites = _sites_per_tile(layout)

    def provider(ty: int, tx: int) -> np.ndarray:
        label = b"test-words/" + f"{ty},{tx}".encode()
        return rng(seed, label).integers(0, 2, size=n_sites, dtype=np.uint8)

    return provider


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fake-words", action="store_true",
                    help="DEBUG: rng stand-in words instead of "
                         "pilots.encode_word (page NOT decodable; never print)")
    args = ap.parse_args(argv)

    t0 = time.time()
    spec = ComposeSpec()
    payload = rng(SEED, b"e011/payload").integers(
        0, 2, size=payload_capacity(spec), dtype=np.uint8)
    provider = fake_word_provider(SEED, spec.pilot) if args.fake_words else None
    composed = compose_page(payload, spec, SEED, page=0, word_provider=provider)

    OUT.mkdir(parents=True, exist_ok=True)
    title = ("paperholo e011 pilot page FAKE-WORDS" if args.fake_words
             else "paperholo e011 pilot page")
    mf = emit_composed(
        composed, OUT / "e011.ps", title=title,
        extra_manifest={
            "artifact": "e011",
            "run": "011.0",
            "word_provider": ("fake-test-words (DEBUG, do not print)"
                              if args.fake_words else "pilots.encode_word"),
        })
    assert mf["ps_bytes"] <= PS_BUDGET_BYTES, \
        f"ps {mf['ps_bytes'] / 1e6:.1f} MB > {PS_BUDGET_BYTES / 1e6:.0f} MB budget"

    if args.fake_words:
        print("WARNING: --fake-words DEBUG page (pilot words are NOT "
              "pilots.encode_word) — do not print")
    n_tiles = (spec.page_cells_yx[0] // spec.pilot.period_cells) \
        * (spec.page_cells_yx[1] // spec.pilot.period_cells)
    print(f"wrote build/e011.ps ({mf['ps_bytes'] / 1e6:.2f} MB, "
          f"{composed.payload_capacity_bits} payload bits, "
          f"{n_tiles} pilot tiles, {time.time() - t0:.1f} s)")
    print(f"sha256 {mf['ps_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

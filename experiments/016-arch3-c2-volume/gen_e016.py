#!/usr/bin/env python3
"""e016 — ARCH-3: the first CODED archive sheet (c2, LDPC + fountain).

One A4 kcell-c2 page (e014 geometry: 3300x2220 cells @300 cpi, p60b6.v3
pilots) whose payload is a REAL single-page fountain volume:

  data (seeded bytes, sha-recorded) -> fountain-v1 (K/N ~ 0.80: ~20% of
  the 1734 interior 64-cell tiles are repair symbols — ANY ~80% of the
  interior tiles recovers ALL data, the on-page confetti/crease budget)
  -> per-tile LDPC r0550 + CRC-32 (conservative rung: the M281's c2
  channel at Canon-4800+ctx is UNMEASURED; 014.2's 1.4-2% was the
  AltaLink print. Rate ladders are set on conservative numbers.)
  -> compose_page -> single imagemask.

Volume seed b"paper-store/exp016-arch3" keys EVERYTHING (pilots, LDPC,
fountain rows, payload scramble). Deterministic + sha-gated; preflight
tests/test_e016.py (determinism, gs pixel-exact render, sim-window
certify + byte-exact frame match).

Print (authorized 2026-07-09): scripts/print_plane.sh
experiments/016-arch3-c2-volume/build/e016.ps  (home M281, raw 9100).
Scan: Canon 4800 grey (the measured c2 footing), 2-3 re-placed scans —
the tile map's more_scans_useful() says when to stop.
"""
from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np

from paperholo import fountain
from paperholo.compose import ComposeSpec, compose_page, emit_composed
from paperholo.modulation import rng
from paperholo.pilots import PilotLayout

SEED = b"paper-store/exp016-arch3"
OUT = Path(__file__).resolve().parent / "build"
PS_BUDGET_BYTES = 30_000_000
K_OVER_N = 0.80                  # repair headroom: ~20% of interior tiles


def make_spec() -> ComposeSpec:
    """e014's frozen page geometry (kcell-c2, v3 words, 6mm+ margins)."""
    return ComposeSpec(layout_version=3, encoding_id="kcell-c2",
                       pilot=PilotLayout(version=3),
                       page_cells_yx=(3300, 2220), x_dots=260, y_dots=208)


def make_vspec() -> fountain.VolumeSpec:
    """Single-page volume at r0550, data sized to K/N ~ 0.80."""
    probe = fountain.VolumeSpec(n_pages=1, data_len_bytes=1, seed=SEED,
                                ldpc_rate_id="r0550",
                                compose_spec=make_spec())
    n_sym = probe.n_symbols_total
    s_bits = probe.symbol_bits
    k = int(K_OVER_N * n_sym)
    data_len = (k * s_bits) // 8
    return fountain.VolumeSpec(n_pages=1, data_len_bytes=data_len,
                               seed=SEED, ldpc_rate_id="r0550",
                               compose_spec=make_spec())


def make_data(vspec: fountain.VolumeSpec) -> bytes:
    """The archived payload: seeded random bytes (self-verifying, frozen
    dtype form — the 012.3 ground-truth rule)."""
    return rng(SEED, b"e016/data").integers(
        0, 256, vspec.data_len_bytes, dtype=np.uint8).tobytes()


def main() -> int:
    t0 = time.time()
    spec = make_spec()
    vspec = make_vspec()
    data = make_data(vspec)
    framed = fountain.encode_volume_pages(data, vspec)[0]
    composed = compose_page(framed["payload_bits"], spec, SEED, page=0)

    OUT.mkdir(parents=True, exist_ok=True)
    mf = emit_composed(
        composed, OUT / "e016.ps",
        title="paperholo e016 ARCH-3 coded c2 volume",
        artifact="e016",
        experiment="016-arch3-c2-volume",
        print_command=("scripts/print_plane.sh "
                       "experiments/016-arch3-c2-volume/build/e016.ps"),
        extra_manifest={
            "artifact": "e016",
            "run": "016.0",
            "volume": {
                "n_pages": 1,
                "data_len_bytes": vspec.data_len_bytes,
                "data_sha256": hashlib.sha256(data).hexdigest(),
                "ldpc_rate_id": "r0550",
                "k_total": vspec.k_total,
                "n_symbols_total": vspec.n_symbols_total,
                "symbol_bits": vspec.symbol_bits,
                "k_over_n": round(vspec.k_total
                                  / vspec.n_symbols_total, 4),
            },
        })
    assert mf["ps_bytes"] <= PS_BUDGET_BYTES
    print(f"wrote build/e016.ps ({mf['ps_bytes'] / 1e6:.2f} MB); volume: "
          f"{vspec.data_len_bytes} data bytes = {vspec.k_total} source + "
          f"{vspec.n_symbols_total - vspec.k_total} repair symbols x "
          f"{vspec.symbol_bits} bits (K/N "
          f"{vspec.k_total / vspec.n_symbols_total:.3f}), r0550, "
          f"{time.time() - t0:.1f} s")
    print(f"data sha256 {hashlib.sha256(data).hexdigest()}")
    print(f"sha256 {mf['ps_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

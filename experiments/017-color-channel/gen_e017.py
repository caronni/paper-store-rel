#!/usr/bin/env python3
"""e017 — ARCH-C: the first CODED COLOR archive sheet (cmy8-c3, LDPC + fountain).

One A4 layout_version-4 page (e012 geometry: 2220x1500 cells @200 cpi,
p60b6 pilot sites, v4 value labels, P1-frozen CM word rendering, P3-frozen
training dust 18/tile) whose payload is a REAL single-page LEVEL-STRATIFIED
fountain volume (COLOR-DESIGN D2: three parallel symbol streams, symbol =
(page, tile, level)):

  data (seeded bytes, sha-recorded) -> fountain-v1 per level (K/N ~ 0.80
  per level: ~20% of each level's 782 interior 64-cell tiles (of the
  840-tile grid; partial edge tiles are fountain-inert) are repair
  symbols — ANY ~80% of a level's interior tiles recovers that level, and
  the volume needs all three) -> per-tile per-LEVEL LDPC + CRC-32 at the
  PROVISIONAL P5 rungs C=r0550 / M=r0550 / Y=r0547 (conservative-doctrine
  placeholders measured at the pessimistic 2 px/dot footing; the Canon RGB
  rescan leg re-freezes them — rungs are VOLUME parameters, not page
  format: regenerating at new rungs keeps layout_version 4, bumps the ps
  golden with a log entry. NOTE: r0547 is the ladder's 0.547-target rung —
  k Z-quantization makes it the same k=2240 as r0550 with an independent
  parity structure; a genuinely lower Y rung (k=2176 = 0.531) is a
  frozen-constants-pass decision) -> compose_page (3 levels, per-plane
  keystreams) -> ONE put_cmyk_bitmap composite (the characterized
  overlap-preserving emission; M281 re-screens ~165 lpi ALWAYS — Layer-0
  freeze; AltaLink honors overlap).

Volume seed b"paper-store/exp017-color" keys EVERYTHING (pilots, dust,
LDPC, fountain rows, per-plane payload scrambles). Deterministic +
sha-gated; preflight tests/test_e017.py (determinism + golden sha, gs
tiffsep per-plane pixel-exact, fully blind clean-channel coded round-trip
byte-exact, sim-regime leg).

Print (pre-registered, experiments/017-color-channel.md — home M281 FIRST,
the MIC-free engine): scripts/print_plane.sh
experiments/017-color-channel/build/e017.ps  (raw 9100).
Scan: Canon 4800 dpi RGB (enhancements off), 2-3 re-placed scans;
pre-decimation to 2400 dpi allowed (016.2-equivalent footing, declared).
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
from paperholo.dust import DustLayout
from paperholo.modulation import rng
from paperholo.pilots import PilotLayout

SEED = b"paper-store/exp017-color"
OUT = Path(__file__).resolve().parent / "build"
PS_BUDGET_BYTES = 40_000_000
K_OVER_N = 0.80                  # per-level repair headroom (~20% of tiles)
# PROVISIONAL per-level rungs (C, M, Y) — probe P5, 2 px/dot anchors; the
# Canon-footing re-freeze happens before print (see module docstring)
RUNGS: tuple[str, str, str] = ("r0550", "r0550", "r0547")


def make_spec() -> ComposeSpec:
    """The frozen ARCH-C page: e012 geometry at layout_version 4 (must equal
    the formats registry row e017-v4-cmy8 — test-asserted)."""
    return ComposeSpec(layout_version=4, encoding_id="cmy8-c3", plane="CMY",
                       pilot=PilotLayout(version=4),
                       page_cells_yx=(2220, 1500),
                       dust=DustLayout(sites_per_tile=18, pure_quota=3))


def make_vspec() -> fountain.VolumeSpec:
    """Single-page level-stratified volume, data sized to K/N ~ 0.80 on the
    summed per-level source capacity (the partition is capacity-proportional,
    so each level lands at ~0.80 individually)."""
    probe = fountain.VolumeSpec(n_pages=1, data_len_bytes=1, seed=SEED,
                                compose_spec=make_spec(), n_levels=3,
                                ldpc_rate_ids=RUNGS)
    cap_bits = sum(probe.source_capacity_bits_level(lv) for lv in range(3))
    data_len = int(K_OVER_N * cap_bits) // 8
    return fountain.VolumeSpec(n_pages=1, data_len_bytes=data_len,
                               seed=SEED, compose_spec=make_spec(),
                               n_levels=3, ldpc_rate_ids=RUNGS)


def make_data(vspec: fountain.VolumeSpec) -> bytes:
    """The archived payload: seeded random bytes (self-verifying, frozen
    dtype form — the 012.3 ground-truth rule)."""
    return rng(SEED, b"e017/data").integers(
        0, 256, vspec.data_len_bytes, dtype=np.uint8).tobytes()


def main() -> int:
    t0 = time.time()
    spec = make_spec()
    vspec = make_vspec()
    data = make_data(vspec)
    framed = fountain.encode_volume_pages(data, vspec)[0]
    composed = compose_page(framed["payload_bits"], spec, SEED, page=0)

    h_dots, w_dots = spec.field_dots_yx
    area_mm2 = (h_dots * 25.4 / 600.0) * (w_dots * 25.4 / 600.0)
    per_level = [{
        "level": "CMY"[lv],
        "ldpc_rate_id": RUNGS[lv],
        "symbol_bits": vspec.symbol_bits_level(lv),
        "k_source": vspec.k_total_level(lv),
        "n_symbols": vspec.n_symbols_total,
        "k_over_n": round(vspec.k_total_level(lv)
                          / vspec.n_symbols_total, 4),
        "data_bytes": vspec.data_len_bytes_level(lv),
    } for lv in range(3)]

    OUT.mkdir(parents=True, exist_ok=True)
    mf = emit_composed(
        composed, OUT / "e017.ps",
        title="paperholo e017 ARCH-C coded cmy8 volume",
        artifact="e017",
        experiment="017-color-channel",
        print_command=("scripts/print_plane.sh "
                       "experiments/017-color-channel/build/e017.ps"),
        extra_manifest={
            "artifact": "e017",
            "run": "017.0",
            "volume": {
                "n_pages": 1,
                "n_levels": 3,
                "data_len_bytes": vspec.data_len_bytes,
                "data_sha256": hashlib.sha256(data).hexdigest(),
                "ldpc_rate_ids": list(RUNGS),
                "per_level": per_level,
                "k_over_n_target": K_OVER_N,
                "net_bits_per_mm2": round(
                    vspec.data_len_bytes * 8 / area_mm2, 2),
            },
        })
    assert mf["ps_bytes"] <= PS_BUDGET_BYTES
    print(f"wrote build/e017.ps ({mf['ps_bytes'] / 1e6:.2f} MB); volume: "
          f"{vspec.data_len_bytes} data bytes over 3 levels x "
          f"{vspec.n_symbols_total} tiles:")
    for e in per_level:
        print(f"  {e['level']}: {e['ldpc_rate_id']}, S={e['symbol_bits']} b, "
              f"K/N {e['k_source']}/{e['n_symbols']} = {e['k_over_n']:.3f}, "
              f"{e['data_bytes']} bytes")
    print(f"net (data bits / field area) = "
          f"{vspec.data_len_bytes * 8 / area_mm2:.1f} b/mm2 at K/N "
          f"{K_OVER_N}; {time.time() - t0:.1f} s")
    print(f"data sha256 {hashlib.sha256(data).hexdigest()}")
    print(f"sha256 {mf['ps_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

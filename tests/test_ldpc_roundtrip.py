"""Layer-3 framing round-trip (paperholo.ldpc tile framing over the
compose payload bijection) + ONE blind sim integration through
acquire.acquire_and_decode.

Framing contract points verified here:
- encode_page fills compose's payload bijection EXACTLY for the e012 page
  geometry (3,237,500 bits; 35x24 = 840 tiles incl. the degenerate corner);
- compose_page -> extract_payload -> gather_tile_llrs -> decode_tile with
  no channel is a bijection (every tile exact);
- per-tile capacity accounting matches the formula (and the page total is
  pinned: 2,189,231 user bits at r0700);
- coverage gating: a ~50%-covered tile is past the measured erasure
  frontier and must FAIL CLEANLY (syndrome+CRC), never certify;
- F9: every crc_ok tile's payload matches GT exactly (blind sim included).

Runs under pytest, or standalone:
env/bin/python tests/test_ldpc_roundtrip.py
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paperholo import acquire, compose, ldpc  # noqa: E402
from paperholo.channel import ChannelParams, print_scan  # noqa: E402
from paperholo.modulation import rng  # noqa: E402
from paperholo.pilots import PilotLayout  # noqa: E402

E012_SEED = b"paper-store/exp012-pilot1"
E012_USER_CAPACITY_R0700 = 2_189_231     # measured page total, pinned
BLIND_SEED = b"paper-store/test-ldpc-blind"

_cache: dict = {}


def _e012_spec() -> compose.ComposeSpec:
    return compose.ComposeSpec(layout_version=3, pilot=PilotLayout(version=3),
                               page_cells_yx=(2220, 1500))


def _e012_encoded() -> tuple:
    if "e012" not in _cache:
        spec = _e012_spec()
        lspec = ldpc.LDPC_LADDER["r0700"]
        ucap = ldpc.page_user_capacity(spec, E012_SEED, lspec)
        user = rng(E012_SEED, b"l3-test/user").integers(
            0, 2, ucap).astype(np.uint8)
        enc = ldpc.encode_page(user, spec, E012_SEED, lspec)
        _cache["e012"] = (spec, lspec, user, enc)
    return _cache["e012"]


def test_e012_fill_and_capacity_accounting() -> None:
    """Exact bijection fill + capacity formula on the real page geometry."""
    spec, lspec, user, enc = _e012_encoded()
    capacity = compose.payload_capacity(spec)
    assert capacity == 3_237_500
    assert enc["payload_bits"].shape == (capacity,)
    tiles = ldpc.tile_grid(spec.page_cells_yx)
    assert len(tiles) == 35 * 24 == len(enc["per_tile"])
    assert enc["user_capacity_bits"] == user.size == E012_USER_CAPACITY_R0700
    total_tx = 0
    off = 0
    for entry in enc["per_tile"]:
        mask = ldpc.tile_shorten_mask(entry["tile_yx"], spec, E012_SEED)
        n_s = int(mask.sum())
        assert entry["n_short"] == n_s
        cap = max(max(lspec.k_bits - n_s, 0) - ldpc.CRC_BITS, 0)
        assert entry["user_bits"] == cap
        assert entry["user_offset"] == off
        assert entry["n_transmitted"] == 4096 - n_s
        off += cap
        total_tx += entry["n_transmitted"]
    assert off == enc["user_capacity_bits"]
    assert total_tx == capacity     # non-shortened slots == payload bijection
    corner = enc["per_tile"][-1]
    assert corner["tile_yx"] == (34, 23) and corner["user_bits"] == 0 \
        and corner["n_short"] > lspec.k_bits     # degenerate overflow tile
    print(f"  e012: 840 tiles fill {capacity} exactly; user capacity "
          f"{off} bits ({off / capacity:.3f} of payload); corner degenerate")


def test_e012_zero_channel_roundtrip() -> None:
    """compose_page -> extract_payload -> gather -> decode: exact, every
    tile, including the degenerate corner (empty payload, ok)."""
    spec, lspec, user, enc = _e012_encoded()
    composed = compose.compose_page(enc["payload_bits"], spec, E012_SEED)
    extracted = compose.extract_payload(composed.cell_values, spec,
                                        E012_SEED, 0)
    assert np.array_equal(extracted, enc["payload_bits"])
    payload_llr = 8.0 * (2.0 * extracted.astype(np.float64) - 1.0)
    pci = np.arange(extracted.size, dtype=np.int64)
    t0 = time.perf_counter()
    results = ldpc.decode_page_tiles(payload_llr, pci, spec, E012_SEED, lspec)
    dt = time.perf_counter() - t0
    assert len(results) == 840
    assert all(r.ok for r in results)
    rec = np.concatenate([r.payload_bits for r in results])
    assert np.array_equal(rec, user)
    assert all(r.n_erased == 0 for r in results)
    print(f"  zero-channel page: 840/840 tiles ok, payload exact "
          f"({840 / dt:.0f} tiles/s clean)")


def test_gather_coverage_and_erasure_gating() -> None:
    """gather_tile_llrs coverage semantics + the coverage failure mode:
    a fragment covering ~half a tile erases ~50% of its slots — beyond the
    measured erasure frontier, the tile must fail cleanly (no false
    certification), while fully-covered tiles decode exactly."""
    spec, lspec, user, enc = _e012_encoded()
    ext = enc["payload_bits"]
    payload_llr_full = 8.0 * (2.0 * ext.astype(np.float64) - 1.0)
    idx_map = compose.payload_index_map(spec, E012_SEED)
    # fragment = absolute cell window rows/cols [600, 1000): tile (10,10)
    # fully inside; tile (15, y) at rows 960..1023 only half covered
    win = idx_map[600:1000, 600:1000]
    pci = win[win >= 0].astype(np.int64)
    pll = payload_llr_full[pci]
    llr, mask, cov = ldpc.gather_tile_llrs(pll, pci, spec, E012_SEED, (10, 10))
    assert cov == 1.0
    res = ldpc.decode_tile(llr, mask, lspec, tile_yx=(10, 10))
    entry = [d for d in enc["per_tile"] if d["tile_yx"] == (10, 10)][0]
    gt = user[entry["user_offset"]:entry["user_offset"] + entry["user_bits"]]
    assert res.ok and np.array_equal(res.payload_bits, gt)
    assert res.n_erased == 0 and res.n_measured == 4096 - entry["n_short"]

    llr2, mask2, cov2 = ldpc.gather_tile_llrs(pll, pci, spec, E012_SEED,
                                              (15, 10))
    assert 0.4 < cov2 < 0.7
    res2 = ldpc.decode_tile(llr2, mask2, lspec, tile_yx=(15, 10))
    assert not res2.ok and res2.payload_bits is None
    assert res2.n_erased + res2.n_measured == int((~mask2).sum())
    assert res2.n_erased > 1000

    llr3, mask3, cov3 = ldpc.gather_tile_llrs(pll, pci, spec, E012_SEED,
                                              (30, 20))
    assert cov3 == 0.0 and not llr3.any()
    sel = ldpc.decode_page_tiles(pll, pci, spec, E012_SEED, lspec,
                                 min_coverage=0.9)
    assert all(r.tile_yx[0] in range(9, 16) and r.tile_yx[1] in range(9, 16)
               for r in sel)
    n_ok = sum(r.ok for r in sel)
    print(f"  fragment window: full tile exact, half tile clean-fail "
          f"(cov {cov2:.2f}, {res2.n_erased} erasures), "
          f"{n_ok}/{len(sel)} gated tiles ok")


def test_blind_sim_integration_r0700() -> None:
    """ONE blind sim round-trip (geometry=True): 300x300-cell v3 page,
    r0700 framing, crop at an odd dot offset + rotation -> full blind
    acquire -> payload_llr -> gather -> decode. Assertions calibrated on
    the measured run (blind BER ~2%, 4 fully-visible tiles all decode in
    2-4 iters; ~50%-covered edge tiles fail cleanly). F9: every ok tile's
    payload matches GT exactly."""
    spec = compose.ComposeSpec(layout_version=3, pilot=PilotLayout(version=3),
                               page_cells_yx=(300, 300))
    lspec = ldpc.LDPC_LADDER["r0700"]
    ucap = ldpc.page_user_capacity(spec, BLIND_SEED, lspec)
    user = rng(BLIND_SEED, b"user").integers(0, 2, ucap).astype(np.uint8)
    enc = ldpc.encode_page(user, spec, BLIND_SEED, lspec)
    composed = compose.compose_page(enc["payload_bits"], spec, BLIND_SEED)
    crop = composed.plane_bits[91:91 + 540, 137:137 + 540]
    scan = print_scan(crop, ChannelParams(seed=42, scan_seed=43,
                                          geometry=True))
    frag = np.ascontiguousarray(np.rot90(scan, -1))
    res = acquire.acquire_and_decode(frag, spec, BLIND_SEED,
                                     max_anchor_sites=120)
    assert res.ok and res.orientation_k == 1 and res.page == 0
    assert res.payload_llr is not None
    assert res.payload_llr.shape == res.payload_bits.shape
    # LLR/hard-bit consistency (house convention: positive = bit 1)
    assert float(np.mean((res.payload_llr > 0) == res.payload_bits)) == 1.0
    ber = float(np.mean(
        res.payload_bits != enc["payload_bits"][res.payload_cell_index]))
    assert ber < 0.08, f"blind payload BER {100 * ber:.1f}%"

    results = ldpc.decode_page_tiles(res.payload_llr, res.payload_cell_index,
                                     spec, BLIND_SEED, lspec,
                                     min_coverage=0.5)
    n_ok = 0
    for r in results:
        entry = [d for d in enc["per_tile"] if d["tile_yx"] == r.tile_yx][0]
        gt = user[entry["user_offset"]:
                  entry["user_offset"] + entry["user_bits"]]
        if r.ok:
            n_ok += 1
            assert np.array_equal(r.payload_bits, gt), \
                f"F9 violation at tile {r.tile_yx}"
        else:
            assert r.payload_bits is None
    # threshold consistency: the 4 fully-visible interior tiles are at
    # ~2% BER < the measured r0700 frontier — they must decode
    full = [r for r in results if r.n_erased == 0]
    assert len(full) >= 4 and all(r.ok for r in full)
    assert n_ok >= 4
    print(f"  blind r0700: BER {100 * ber:.2f}%, {n_ok}/{len(results)} "
          f"gated tiles certified (F9 exact), "
          f"{len(full)} fully-covered all ok")


if __name__ == "__main__":
    for fn in [test_e012_fill_and_capacity_accounting,
               test_e012_zero_channel_roundtrip,
               test_gather_coverage_and_erasure_gating,
               test_blind_sim_integration_r0700]:
        print(fn.__name__)
        fn()
    print("all ldpc roundtrip tests passed")

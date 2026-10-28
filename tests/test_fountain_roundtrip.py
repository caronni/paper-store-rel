"""Layer-4 multi-page round-trips: fountain -> ldpc -> compose and back,
plus the FIRST full-stack blind recovery in the project's history
(modulation -> pilots -> LDPC -> fountain, one call chain, no genie).

Zero-channel volume (e012 geometry, 3 pages, 480 kB = 60.0% of source
capacity at r0700): volume_encode -> ldpc.encode_page -> compose_page ->
extract_payload -> decode_page_tiles on perfect LLRs -> tiles_to_symbols ->
volume_decode == data exactly. R2 slice: drop ENTIRE page 1 (lost sheet) —
the round-robin ESI leaves 1564 certified symbols >= k_total 1409 + 155
margin, GE recovers the volume exactly; drop pages 1 AND 2 -> clean None
with honest per-block diagnostics and partial data.

Runs under pytest, or standalone:
env/bin/python tests/test_fountain_roundtrip.py
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paperholo import acquire, compose, fountain, ldpc  # noqa: E402
from paperholo.channel import ChannelParams, print_scan  # noqa: E402
from paperholo.modulation import rng  # noqa: E402
from paperholo.pilots import PilotLayout  # noqa: E402

E012_SEED = b"paper-store/exp012-pilot1"
BLIND_SEED = b"paper-store/test-fountain-blind"


def test_three_page_volume_zero_channel_and_r2_slice() -> None:
    """3-page e012-geometry volume, zero channel: exact end-to-end identity
    through the full framing stack, then the R2 fragment-recovery property
    at page granularity (drop a whole sheet)."""
    vs = fountain.VolumeSpec(n_pages=3, data_len_bytes=480_000,
                             seed=E012_SEED, ldpc_rate_id="r0700")
    geo = fountain.volume_geometry(vs)
    assert vs.k_total == 1409 and vs.n_blocks == 1
    assert vs.n_symbols_total == 2346
    data = rng(vs.seed, b"l4-test/data").integers(
        0, 256, vs.data_len_bytes, dtype=np.uint8).tobytes()
    t0 = time.perf_counter()
    enc = fountain.volume_encode(data, vs)

    all_results: list[tuple[int, ldpc.TileResult]] = []
    for page in range(vs.n_pages):
        le = ldpc.encode_page(enc.page_user_bits[page], vs.compose_spec,
                              vs.seed, vs.ldpc_spec)
        composed = compose.compose_page(le["payload_bits"], vs.compose_spec,
                                        vs.seed, page=page)
        extracted = compose.extract_payload(composed.cell_values,
                                            vs.compose_spec, vs.seed, page)
        assert np.array_equal(extracted, le["payload_bits"])
        llr = 4.0 * (2.0 * extracted.astype(np.float64) - 1.0)
        pci = np.arange(extracted.size, dtype=np.int64)
        results = ldpc.decode_page_tiles(llr, pci, vs.compose_spec, vs.seed,
                                         vs.ldpc_spec)
        assert len(results) == 840 and all(r.ok for r in results)
        all_results += [(page, r) for r in results]
    dt = time.perf_counter() - t0

    # full volume: all 2346 symbols certified -> systematic fast path
    syms = fountain.tiles_to_symbols(all_results, vs)
    assert len(syms) == vs.n_symbols_total
    out, diag = fountain.volume_decode(syms, vs)
    assert out == data
    assert diag["solved_all"] and diag["blocks"][0]["systematic"]

    # R2: page 1 lost entirely -> 1564 symbols (782 source + 782 repair),
    # GE must still recover the exact volume
    syms_drop = fountain.tiles_to_symbols(
        [(p, r) for p, r in all_results if p != 1], vs)
    assert len(syms_drop) == 2 * 782
    out2, diag2 = fountain.volume_decode(syms_drop, vs)
    assert out2 == data
    d0 = diag2["blocks"][0]
    assert not d0["systematic"] and d0["rank"] == vs.k_total

    # too much lost: only page 0 (782 < 1409) -> honest None + partial
    syms_p0 = fountain.tiles_to_symbols(
        [(p, r) for p, r in all_results if p == 0], vs)
    out3, diag3 = fountain.volume_decode(syms_p0, vs)
    assert out3 is None and not diag3["solved_all"]
    assert diag3["blocks"][0]["rank"] == 782
    assert len(diag3["partial_data"]) == vs.data_len_bytes
    assert int(diag3["symbol_recovered"].sum()) == 0    # block-granular honesty
    print(f"  3-page e012 volume ({vs.data_len_bytes} B = "
          f"{vs.data_bits / geo['source_capacity_bits']:.1%} of source cap): "
          f"exact; page-1 drop -> GE exact (1564 recv/1409 needed); "
          f"page-0-only -> honest None ({dt:.0f}s framing)")


def test_blind_two_page_fountain_recovery() -> None:
    """FIRST full-stack blind recovery: modulation -> pilots -> LDPC ->
    fountain in one chain.

    FOOTING LABELS (explicit, per the measurement doctrine):
    - channel: paperholo.channel.print_scan, geometry=True (stepped warp,
      comb, y-scale — the adversarial sim geometry), DISTINCT print/scan
      seeds per page (independent warp/noise draws: page 0 seeds 100/200,
      page 1 seeds 101/201);
    - receiver: FULLY BLIND — acquire.acquire_and_decode with no genie
      inputs (lattice-FFT lock, v3 pilot-word search, anchor warp repair);
      page identity comes from the decoded pilot flat counter
      (AcquireResult.page), NOT from test bookkeeping — asserted equal to
      the composed page index, and that value is what keys the symbol map;
    - orientation: page 1's scan is rotated 90 deg before acquisition
      (blind orientation detection exercised end-to-end);
    - volume: 2 pages of 300x300 cells (the small-page test idiom) at
      r0550, k_total = 20 source symbols of 32 tiles; the fountain margin
      is exercised a second time by decoding from a random 24-symbol subset
      (GE path, sources erased).
    Assertions calibrated on the measured run: blind payload BER
    2.85%/2.04%, 16/16 interior tiles certified per page."""
    spec = compose.ComposeSpec(layout_version=3, pilot=PilotLayout(version=3),
                               page_cells_yx=(300, 300))
    vs = fountain.VolumeSpec(n_pages=2, data_len_bytes=5000, seed=BLIND_SEED,
                             ldpc_rate_id="r0550", compose_spec=spec)
    assert vs.k_total == 20 and vs.n_symbols_total == 32
    data = rng(BLIND_SEED, b"l4-blind/data").integers(
        0, 256, vs.data_len_bytes, dtype=np.uint8).tobytes()
    enc = fountain.volume_encode(data, vs)

    collected: list[tuple[int, ldpc.TileResult]] = []
    for page in range(vs.n_pages):
        le = ldpc.encode_page(enc.page_user_bits[page], spec, BLIND_SEED,
                              vs.ldpc_spec)
        composed = compose.compose_page(le["payload_bits"], spec, BLIND_SEED,
                                        page=page)
        scan = print_scan(composed.plane_bits,
                          ChannelParams(seed=100 + page, scan_seed=200 + page,
                                        geometry=True))
        if page == 1:
            scan = np.ascontiguousarray(np.rot90(scan, 1))
        res = acquire.acquire_and_decode(scan, spec, BLIND_SEED,
                                         max_anchor_sites=120)
        assert res.ok, f"blind acquisition failed on page {page}"
        assert res.page == page, "counter-derived page identity wrong"
        assert res.orientation_k == (3 if page == 1 else 0)
        ber = float(np.mean(
            res.payload_bits != le["payload_bits"][res.payload_cell_index]))
        assert ber < 0.08, f"page {page} blind BER {100 * ber:.1f}%"
        results = ldpc.decode_page_tiles(res.payload_llr,
                                         res.payload_cell_index, spec,
                                         BLIND_SEED, vs.ldpc_spec,
                                         min_coverage=0.3)
        n_int_ok = sum(
            r.ok for r in results
            if fountain.esi_of_tile(vs, res.page, r.tile_yx) is not None)
        assert n_int_ok >= 14, f"page {page}: {n_int_ok}/16 interior certified"
        # res.page (the DECODED counter value) keys the symbol map:
        collected += [(res.page, r) for r in results]
        print(f"  page {page}: blind BER {100 * ber:.2f}%, "
              f"{n_int_ok}/16 interior tiles certified "
              f"(rot90={res.orientation_k})")

    syms = fountain.tiles_to_symbols(collected, vs)
    assert len(syms) >= 28
    out, diag = fountain.volume_decode(syms, vs)
    assert out == data, "full-stack blind volume recovery failed"

    # fountain margin under tile loss: random 24-symbol subset (drops
    # sources -> GE path) must still recover exactly
    g = rng(BLIND_SEED, b"subset")
    keys = sorted(syms)
    keep = [keys[j] for j in g.choice(len(keys), size=24, replace=False)]
    out2, diag2 = fountain.volume_decode({k: syms[k] for k in keep}, vs)
    assert out2 == data
    assert diag2["blocks"][0]["rank"] == vs.k_total
    print(f"  volume: {len(syms)}/32 certified symbols -> data exact "
          f"(k_total 20); random 24-symbol subset -> GE exact — "
          f"first full-stack blind recovery")


if __name__ == "__main__":
    for fn in [test_three_page_volume_zero_channel_and_r2_slice,
               test_blind_two_page_fountain_recovery]:
        print(fn.__name__)
        fn()
    print("all fountain roundtrip tests passed")

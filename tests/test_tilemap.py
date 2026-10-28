"""PageDecodeState (paperholo.tilemap) + the page_decode driver.

Full-stack accumulation semantics: multi-scan observations kept separate
(F6, 012.3/013 negative results honored), four merge policies, LDPC decode
with CRC certification, F9 backfill verified in BOTH domains (payload-LLR
pins and detection-domain known cells vs the printed page), fountain export,
and the window-tiling whole-scan driver.

Runs under pytest, or standalone: env/bin/python tests/test_tilemap.py
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paperholo import acquire, compose, formats, ldpc, tilemap  # noqa: E402
from paperholo.channel import ChannelParams, print_scan  # noqa: E402
from paperholo.modulation import rng  # noqa: E402
from paperholo.pilots import PilotLayout  # noqa: E402

SEED = b"paper-store/test-tilemap"
RATE = "r0700"

_cache: dict = {}


def _framed_page() -> tuple[compose.ComposeSpec, dict, np.ndarray,
                            compose.ComposedPage]:
    """240-cell c3 page carrying a REAL LDPC-framed payload."""
    if "page" not in _cache:
        spec = compose.ComposeSpec(layout_version=3,
                                   pilot=PilotLayout(version=3),
                                   page_cells_yx=(240, 240))
        ls = ldpc.LDPC_LADDER[RATE]
        n_user = sum(
            ldpc.tile_user_capacity(ldpc.tile_shorten_mask(t, spec, SEED),
                                    ls)
            for t in ldpc.tile_grid(spec.page_cells_yx))
        user = rng(SEED, b"user").integers(0, 2, n_user, dtype=np.uint8)
        framed = ldpc.encode_page(user, spec, SEED, ls)
        cp = compose.compose_page(framed["payload_bits"], spec, SEED,
                                  page=0)
        _cache["page"] = (spec, framed, user, cp)
    return _cache["page"]


def _state_with_scans(n_scans: int = 3) -> tilemap.PageDecodeState:
    spec, _, _, cp = _framed_page()
    key = f"state{n_scans}"
    if key not in _cache:
        pds = tilemap.PageDecodeState(spec, SEED, page=0)
        for i in range(n_scans):
            scan = print_scan(cp.plane_bits,
                              ChannelParams(seed=50, scan_seed=51 + 100 * i,
                                            geometry=True))
            res = acquire.acquire_and_decode(scan, spec, SEED)
            assert res.ok, res.diagnostics
            pds.add_acquire_result(f"scan{i}", res)
        _cache[key] = pds
    return _cache[key]


def _fresh_copy(pds: tilemap.PageDecodeState) -> tilemap.PageDecodeState:
    return pds.copy()


def test_policies_certify_byte_exact() -> None:
    """All four merge policies certify every tile; certified user bits are
    byte-exact against the encoder's frame; provenance recorded."""
    spec, framed, user, _ = _framed_page()
    base = _state_with_scans()
    gt = {tuple(e["tile_yx"]): (e["user_offset"], e["user_bits"])
          for e in framed["per_tile"]}
    for policy in ("best_scan", "best_per_tile", "weighted_sum", "sum"):
        m = _fresh_copy(base)
        counts = m.decode_tiles(RATE, policy=policy)
        assert counts["certified"] == len(m.tiles), (policy, counts)
        for t, st in m.tiles.items():
            off, cap = gt[t]
            assert np.array_equal(st.payload_bits, user[off:off + cap]), \
                (policy, t)
            assert st.rate_id == RATE and st.policy == policy
        if policy in ("best_scan", "best_per_tile"):
            assert all(st.scan_id in m.scans for st in m.tiles.values())
        # idempotence: a second decode pass skips certified tiles
        again = m.decode_tiles(RATE, policy=policy,
                               tiles=list(m.tiles))
        assert again["skipped_certified"] == len(m.tiles)
    print(f"  4 policies x {len(base.tiles)} tiles certified byte-exact")


def test_f9_backfill_both_domains() -> None:
    """Certified knowledge: payload-domain pins match the re-encoded frame;
    detection-domain known cells match the PRINTED page exactly."""
    spec, framed, _, cp = _framed_page()
    m = _fresh_copy(_state_with_scans())
    m.decode_tiles(RATE, policy="best_scan")
    idx, llr = m.certified_payload_llrs()
    assert idx.size > 0 and np.all(np.isinf(llr))
    gt_payload = framed["payload_bits"]
    assert np.array_equal((llr > 0).astype(np.uint8), gt_payload[idx])
    y, x, bits = m.known_cell_values()
    assert np.array_equal(bits, cp.cell_values[y, x]), \
        "detection-domain backfill disagrees with the printed page"
    print(f"  F9: {idx.size} payload pins + {y.size} known cells exact")


def test_fountain_export_and_worklist() -> None:
    """certified_results feeds fountain-style consumption; pending_tiles
    empties on full certification."""
    m = _fresh_copy(_state_with_scans())
    assert len(m.pending_tiles()) == len(m.tiles)
    m.decode_tiles(RATE, policy="best_scan")
    assert m.pending_tiles() == []
    stream = list(m.certified_results())
    assert len(stream) == len(m.tiles)
    page, tr = stream[0]
    assert page == 0 and tr.ok and tr.payload_bits is not None
    s = m.summary()
    assert s["tiles"] == {"certified": len(m.tiles)}
    print(f"  fountain export {len(stream)} tiles; worklist drained; "
          f"certified bits {s['certified_bits']}")


def test_scan_quality_and_extend() -> None:
    """Per-scan pilot quality from tile_words; window extend keeps the
    higher-|LLR| observation and the better word outcome."""
    m = _state_with_scans()
    for obs in m.scans.values():
        assert 0.0 <= obs.pilot_ber_est < 0.10   # healthy c3 sim scans
        q = obs.tile_quality((1, 1))
        assert q is None or 0.0 <= q < 0.15
    obs = list(m.scans.values())[0]
    n0 = obs.payload_cell_index.size
    idx = obs.payload_cell_index[:10]
    weak = np.full(10, 0.001)
    before = obs.payload_llr[:10].copy()
    obs.extend(idx, weak, {})
    assert obs.payload_cell_index.size == n0        # no duplicates added
    got = obs.payload_llr[np.searchsorted(obs.payload_cell_index, idx)]
    assert np.array_equal(got, before)              # stronger LLRs kept
    print(f"  scan quality estimates sane; extend dedupes by |LLR|")


def test_page_decode_driver_windows() -> None:
    """Whole-scan driver: identify format, tile windows, fill the map,
    certify everything (zero-channel image at 2 px/dot; window grid must
    cover the page edges)."""
    spec, framed, user, cp = _framed_page()
    img = np.repeat(np.repeat((1.0 - cp.plane_bits).astype(np.float64),
                              2, 0), 2, 1)
    cands = [formats.FormatDescriptor("tmap-v3-c3", SEED, 3, "kcell-c3",
                                      (240, 240))]
    ident, state = formats.page_decode(img, scan_id="s0", candidates=cands,
                                       scan_dpi=1200.0, window_cells=150,
                                       overlap_cells=30)
    assert ident.ok and ident.fmt.format_id == "tmap-v3-c3"
    assert ident.diagnostics["n_windows_ok"] >= 4
    counts = state.decode_tiles(RATE, policy="best_scan")
    assert counts["certified"] == len(state.tiles), counts
    gt = {tuple(e["tile_yx"]): (e["user_offset"], e["user_bits"])
          for e in framed["per_tile"]}
    for t, st in state.tiles.items():
        off, cap = gt[t]
        assert np.array_equal(st.payload_bits, user[off:off + cap])
    print(f"  page_decode: {ident.diagnostics['n_windows_ok']}/"
          f"{ident.diagnostics['n_windows_tried']} windows, "
          f"{counts['certified']} tiles certified byte-exact")


def test_volume_scans_wanted() -> None:
    """The OUTER F6 loop: fountain rank deficit -> ranked page re-asks;
    empty once the volume decodes."""
    from paperholo import fountain
    probe = fountain.VolumeSpec(n_pages=1, data_len_bytes=1, seed=b"t/vsw")
    K = int(0.9 * probe.n_symbols_total)
    vs = fountain.VolumeSpec(n_pages=1,
                             data_len_bytes=(K * probe.symbol_bits) // 8,
                             seed=b"t/vsw")
    data = rng(b"t/vsw", b"data").integers(
        0, 256, vs.data_len_bytes, dtype=np.uint8).tobytes()
    framed = fountain.encode_volume_pages(data, vs)[0]
    st = tilemap.PageDecodeState(vs.compose_spec, vs.seed, page=0)
    gt = {tuple(e["tile_yx"]): (e["user_offset"], e["user_bits"])
          for e in framed["per_tile"]}
    user = fountain.volume_encode(data, vs).page_user_bits[0]
    interior = fountain.interior_tiles(vs.compose_spec)
    for i, t in enumerate(interior):          # certify 1/3 -> under-ranked
        if i % 3 == 0:
            off, cap = gt[t]
            st.tiles[t].status = "certified"
            st.tiles[t].payload_bits = user[off:off + cap]
    wanted = tilemap.volume_scans_wanted({0: st}, vs)
    assert wanted and wanted[0][0] == 0
    assert wanted[0][1]["volume_deficit_symbols"] > 0
    for t in interior:                        # certify all -> volume solves
        off, cap = gt[t]
        st.tiles[t].status = "certified"
        st.tiles[t].payload_bits = user[off:off + cap]
    assert tilemap.volume_scans_wanted({0: st}, vs) == []
    print("  volume loop: under-ranked -> re-ask ranked; solved -> empty")


if __name__ == "__main__":
    for fn in (test_policies_certify_byte_exact,
               test_f9_backfill_both_domains,
               test_fountain_export_and_worklist,
               test_scan_quality_and_extend,
               test_page_decode_driver_windows,
               test_volume_scans_wanted):
        t0 = time.time()
        fn()
        print(f"PASS {fn.__name__} ({time.time() - t0:.1f}s)")

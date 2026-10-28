"""Layer-4 fountain codec tests (paperholo.fountain, fountain-v1).

Format-axis anchors pinned here:
- e012-geometry volume constants: S = 2727 user bits/symbol at r0700,
  782 interior (symbol-bearing) tiles/page, fountain-inert capacity loss
  2.33% (edge tiles) + 0.26% (interior zero pad);
- generator-row golden: sha256 of the first 8 block-0 repair rows for the
  frozen e012 3-page vspec (if this moves you changed the fountain format —
  it is payload-interpretation, document and re-anchor deliberately);
- geometric ESI bijection: every interior tile maps to exactly one
  (block, in_block_index), blocks balanced to +-1, round-robin interleave,
  source symbols == the first k_total global tile indices (source-first);
- overhead curve at K = 512 (dense-RLF theory: ~29% at K, prod(1-2^-i)
  tails above): measured 59/200, 155/200, 195/200, 200/200 at K/+2/+5/+16;
- GE speed at K = 4096 with ~2000 dense rows (bit-packed Gauss-Jordan).

Garbage-in is OUT OF CONTRACT: the fountain consumes CERTIFIED tiles only
(ldpc's CRC-32 F9 owns cleanliness). A corrupted symbol value decodes to
wrong data with no flag — asserted below as documentation; the real gate is
tiles_to_symbols dropping every non-ok TileResult, tested here.

Runs under pytest, or standalone:
env/bin/python tests/test_fountain.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paperholo import compose, fountain, ldpc  # noqa: E402
from paperholo.modulation import rng  # noqa: E402
from paperholo.pilots import PilotLayout  # noqa: E402

E012_SEED = b"paper-store/exp012-pilot1"
# frozen anchors (e012 page, r0700):
E012_S_BITS = 2727
E012_INTERIOR = 782
GOLDEN_ROWS_SHA = ("fb79e70417212f842ef189c6188e7f33"
                   "d7dafa75d85019190e3c4c2a44f38fbd")

SMALL_SEED = b"paper-store/test-fountain-small"

_cache: dict = {}


def _small_cspec() -> compose.ComposeSpec:
    return compose.ComposeSpec(layout_version=3, pilot=PilotLayout(version=3),
                               page_cells_yx=(300, 300))


def _e012_vspec() -> fountain.VolumeSpec:
    """The frozen golden-anchor vspec: 3 e012 pages, 480 kB (60.0% of source
    capacity), r0700 -> k_total = 1409, single block."""
    return fountain.VolumeSpec(n_pages=3, data_len_bytes=480_000,
                               seed=E012_SEED, ldpc_rate_id="r0700")


def _small_vspec() -> fountain.VolumeSpec:
    """2-page 300x300-cell r0550 volume, k_total = 20 of 32 symbols."""
    return fountain.VolumeSpec(n_pages=2, data_len_bytes=5000,
                               seed=SMALL_SEED, ldpc_rate_id="r0550",
                               compose_spec=_small_cspec())


def _small_encoded() -> tuple:
    if "small" not in _cache:
        vs = _small_vspec()
        data = rng(vs.seed, b"l4-test/data").integers(
            0, 256, vs.data_len_bytes, dtype=np.uint8).tobytes()
        _cache["small"] = (vs, data, fountain.volume_encode(data, vs))
    return _cache["small"]


def _all_source_symbols(vs: fountain.VolumeSpec,
                        enc: fountain.VolumeEncoding) -> dict:
    return {(t % vs.n_blocks, t // vs.n_blocks):
            enc.symbol(t % vs.n_blocks, t // vs.n_blocks)
            for t in range(vs.k_total)}


def test_pack_unpack_bits() -> None:
    """_pack_bits_2d frozen packing: column c = bit (c & 63) of word
    (c >> 6); round-trips exactly at non-multiple-of-64 widths."""
    g = rng(SMALL_SEED, b"packbits")
    for width in (1, 63, 64, 65, 200, 512):
        bits = g.integers(0, 2, size=(5, width)).astype(np.uint8)
        packed = fountain._pack_bits_2d(bits)
        assert packed.shape == (5, -(-width // 64))
        assert np.array_equal(fountain._unpack_bits_2d(packed, width), bits)
    one = np.zeros((1, 130), np.uint8)
    one[0, 129] = 1                      # column 129 = word 2, bit 1
    p = fountain._pack_bits_2d(one)
    assert p[0, 2] == np.uint64(2) and not p[0, :2].any()
    print("  pack/unpack: exact at widths 1..512, column mapping pinned")


def test_e012_volume_geometry_constants() -> None:
    """e012-geometry volume constants (frozen): S, interior tiles/page,
    fountain-inert capacity loss; capacity accounting consistency."""
    vs = _e012_vspec()
    geo = fountain.volume_geometry(vs)
    assert geo["symbol_bits"] == E012_S_BITS == vs.symbol_bits
    assert geo["n_interior_tiles_per_page"] == E012_INTERIOR
    assert geo["page_user_capacity_bits"] == 2_189_231   # ldpc pinned total
    assert abs(geo["fountain_inert_capacity_fraction"] - 0.02327) < 2e-4
    assert abs(geo["pad_capacity_fraction"] - 0.00263) < 2e-4
    assert vs.n_symbols_total == 3 * E012_INTERIOR == 2346
    assert vs.k_total == 1409 and vs.n_blocks == 1
    assert vs.k_per_block == (1409,)
    assert vs.source_capacity_bits == 2346 * E012_S_BITS
    # interior tiles are exactly the full-64x64 tiles, raster order
    interior = geo["interior_tile_yx"]
    assert len(interior) == E012_INTERIOR
    assert all(ty < 34 and tx < 23 for ty, tx in interior)
    assert interior == tuple(sorted(interior))
    print(f"  e012 volume: S={E012_S_BITS}, {E012_INTERIOR} interior/page, "
          f"inert {100 * geo['fountain_inert_capacity_fraction']:.2f}% + "
          f"pad {100 * geo['pad_capacity_fraction']:.2f}%")


def test_esi_bijection_and_source_first() -> None:
    """Geometric ESI on a MULTI-block volume: every interior tile of every
    page maps to a unique (block, i); blocks balanced to +-1; round-robin
    interleave (consecutive global tiles hit consecutive blocks); source
    set == first k_total global tiles; tile_of_symbol inverts."""
    cs = _small_cspec()
    probe = fountain.VolumeSpec(n_pages=304, data_len_bytes=1,
                                seed=SMALL_SEED, ldpc_rate_id="r0550",
                                compose_spec=cs)
    s = probe.symbol_bits
    # k_total = 4801 -> 2 blocks, k_per_block = (2401, 2400)
    vs = fountain.VolumeSpec(n_pages=304,
                             data_len_bytes=(4800 * s) // 8 + 1,
                             seed=SMALL_SEED, ldpc_rate_id="r0550",
                             compose_spec=cs)
    assert vs.k_total == 4801 and vs.n_blocks == 2
    assert vs.k_per_block == (2401, 2400)
    geo = fountain.volume_geometry(vs)
    n_int = geo["n_interior_tiles_per_page"]
    assert n_int == 16 and vs.n_symbols_total == 4864

    seen: dict = {}
    n_none = 0
    for page in range(vs.n_pages):
        for tile in ldpc.tile_grid(cs.page_cells_yx):
            key = fountain.esi_of_tile(vs, page, tile)
            if key is None:
                n_none += 1
                assert tile not in geo["interior_local_index"]
                continue
            assert key not in seen, f"ESI collision at {key}"
            seen[key] = (page, tile)
            assert fountain.tile_of_symbol(vs, *key) == (page, tile)
    assert len(seen) == vs.n_symbols_total
    assert n_none == vs.n_pages * (25 - 16)          # 9 edge tiles/page
    # balance + round-robin
    counts = np.bincount([b for b, _ in seen], minlength=2)
    assert counts.max() - counts.min() <= 1
    for t in range(200):
        b, i = t % 2, t // 2
        assert (b, i) in seen
    # source-first: i < K_b exactly for the first k_total global tiles
    for t in range(vs.n_symbols_total):
        b, i = t % 2, t // 2
        assert (i < vs.k_per_block[b]) == (t < vs.k_total)
    try:
        fountain.esi_of_tile(vs, vs.n_pages, (1, 1))
        raise AssertionError("page out of range must raise")
    except ValueError:
        pass
    print(f"  ESI: {len(seen)} symbols bijective over 2 blocks "
          f"({counts.tolist()}), source-first verified over all tiles")


def test_generator_rows_golden() -> None:
    """Generator determinism + systematic unit rows + the frozen sha256
    anchor of block-0 repair rows i = K_0..K_0+7 on the e012 vspec."""
    vs = _e012_vspec()
    k0 = vs.k_per_block[0]
    for i in (0, 1, 700, k0 - 1):
        row = fountain.generator_row(vs, 0, i)
        assert row.shape == (k0,) and row.sum() == 1 and row[i] == 1
    rows = [fountain.generator_row(vs, 0, i) for i in range(k0, k0 + 8)]
    for i, row in zip(range(k0, k0 + 8), rows):
        assert row.shape == (k0,) and set(np.unique(row)) <= {0, 1}
        assert np.array_equal(row, fountain.generator_row(vs, 0, i))
        assert 0.4 < row.mean() < 0.6            # dense ~K/2
    sha = hashlib.sha256(np.concatenate(rows).tobytes()).hexdigest()
    assert sha == GOLDEN_ROWS_SHA, (
        f"fountain-v1 generator rows moved: {sha} (payload-interpretation "
        "format change — re-anchor deliberately, never silently)")
    print(f"  generator golden: sha256 {sha[:16]}.. pinned, unit rows exact")


def test_encode_framing_agrees_with_ldpc_accounting() -> None:
    """The symbol<->tile framing agrees with ldpc.encode_page's per_tile
    accounting EXACTLY: interior tile (b,i)'s symbol sits in user bits
    [user_offset, user_offset+S), the rest of its capacity is zero pad;
    edge tiles are all-zero (fountain-inert)."""
    vs, data, enc = _small_encoded()
    s = vs.symbol_bits
    for page in range(vs.n_pages):
        user = enc.page_user_bits[page]
        le = ldpc.encode_page(user, vs.compose_spec, vs.seed, vs.ldpc_spec)
        assert user.size == le["user_capacity_bits"]
        for entry in le["per_tile"]:
            seg = user[entry["user_offset"]:
                       entry["user_offset"] + entry["user_bits"]]
            key = fountain.esi_of_tile(vs, page, entry["tile_yx"])
            if key is None:
                assert not seg.any(), f"inert tile {entry['tile_yx']} not zero"
            else:
                assert entry["user_bits"] >= s
                assert np.array_equal(seg[:s], enc.symbol(*key))
                assert not seg[s:].any(), "pad bits must be zero"
    print(f"  framing: {vs.n_pages} pages x 25 tiles agree with encode_page "
          f"accounting (S={s}, pads zero, edges zero)")


def test_systematic_identity_ge_and_partial() -> None:
    """encode -> decode identity from ALL source symbols (systematic fast
    path, no GE); GE path with erased sources + repair symbols; under-rank
    -> honest None + partial diagnostics."""
    vs, data, enc = _small_encoded()
    syms = _all_source_symbols(vs, enc)
    out, diag = fountain.volume_decode(syms, vs)
    assert out == data
    assert diag["solved_all"] and diag["blocks"][0]["systematic"]
    assert diag["blocks"][0]["rank"] == vs.k_total

    # GE: drop 5 sources, add 8 repair symbols
    ge_syms = dict(syms)
    for t in (0, 3, 7, 11, 19):
        del ge_syms[(t % vs.n_blocks, t // vs.n_blocks)]
    for t in range(vs.k_total, vs.k_total + 8):
        b, i = t % vs.n_blocks, t // vs.n_blocks
        ge_syms[(b, i)] = enc.symbol(b, i)
    out2, diag2 = fountain.volume_decode(ge_syms, vs)
    assert out2 == data
    d0 = diag2["blocks"][0]
    assert not d0["systematic"] and d0["rank"] == 20 and d0["received"] == 23

    # under-rank: honest failure with partial data
    few = {k: v for k, v in ge_syms.items() if k[1] < 10}
    out3, diag3 = fountain.volume_decode(few, vs)
    assert out3 is None and not diag3["solved_all"]
    assert diag3["blocks"][0]["rank"] < vs.k_total
    assert diag3["solved_blocks"] == []
    assert len(diag3["partial_data"]) == vs.data_len_bytes
    assert diag3["symbol_recovered"].shape == (vs.k_total,)
    assert not diag3["symbol_recovered"].any()

    # DOCUMENTED out-of-contract: a corrupted symbol value (bypassing the
    # CRC gate) decodes to WRONG data with no flag — F9 upstream owns
    # cleanliness; the in-contract gate is tiles_to_symbols (next test).
    bad = dict(syms)
    v = bad[(0, 2)].copy()
    v[17] ^= 1
    bad[(0, 2)] = v
    out4, diag4 = fountain.volume_decode(bad, vs)
    assert diag4["solved_all"] and out4 is not None and out4 != data
    print("  systematic exact / GE exact (rank 20 of 23 recv) / "
          "under-rank honest None / garbage-in documented")


def test_tiles_to_symbols_certified_only() -> None:
    """The F9 seam: tiles_to_symbols consumes CERTIFIED tiles only — drops
    non-ok results, fountain-inert (edge) tiles, out-of-volume pages;
    dedupes rescans first-wins; strips the zero pad; raises on a payload
    shorter than S (volume-descriptor mismatch)."""
    vs, data, enc = _small_encoded()
    s = vs.symbol_bits
    geo = fountain.volume_geometry(vs)
    cap = geo["tile_cap"]

    def tr(tile, payload, ok=True):
        return ldpc.TileResult(tile_yx=tile, ok=ok, crc_ok=ok,
                               syndrome_ok=ok,
                               payload_bits=payload if ok else None,
                               n_iters=1, n_erased=0, n_measured=1)

    def tile_payload(page, tile):
        key = fountain.esi_of_tile(vs, page, tile)
        vec = np.zeros(cap[tile], np.uint8)
        vec[:s] = enc.symbol(*key)
        return vec

    good = tile_payload(0, (0, 0))
    corrupt = good.copy()
    corrupt[0] ^= 1
    results = [
        (0, tr((0, 0), good)),                        # kept
        (0, tr((0, 0), corrupt)),                     # duplicate: first wins
        (0, tr((1, 1), None, ok=False)),              # NON-OK: dropped
        (0, tr((4, 4), np.zeros(cap[(4, 4)], np.uint8))),  # inert edge tile
        (7, tr((1, 1), good)),                        # page outside volume
        (1, tr((2, 3), tile_payload(1, (2, 3)))),     # kept (page 1)
    ]
    syms = fountain.tiles_to_symbols(results, vs)
    k00 = fountain.esi_of_tile(vs, 0, (0, 0))
    k123 = fountain.esi_of_tile(vs, 1, (2, 3))
    assert set(syms) == {k00, k123}
    assert np.array_equal(syms[k00], enc.symbol(*k00))      # first won
    assert syms[k00].shape == (s,)                          # pad stripped
    assert np.array_equal(syms[k123], enc.symbol(*k123))
    try:
        fountain.tiles_to_symbols([(0, tr((0, 0), good[:s - 1]))], vs)
        raise AssertionError("short payload must raise")
    except ValueError:
        pass
    print(f"  tiles_to_symbols: 2/6 kept (non-ok, inert, foreign page, "
          f"duplicate dropped); pad stripped to S={s}")


def test_data_len_roundtrip_odd_sizes() -> None:
    """Non-multiple-of-S data lengths round-trip exactly (pad stripped by
    data_len_bytes); capacity overflow raises; bad specs raise."""
    cs = _small_cspec()
    for n_bytes in (1, 100, 5227):
        vs = fountain.VolumeSpec(n_pages=2, data_len_bytes=n_bytes,
                                 seed=SMALL_SEED, ldpc_rate_id="r0550",
                                 compose_spec=cs)
        data = rng(SMALL_SEED, b"odd" + str(n_bytes).encode()).integers(
            0, 256, n_bytes, dtype=np.uint8).tobytes()
        enc = fountain.volume_encode(data, vs)
        assert vs.k_total * vs.symbol_bits >= n_bytes * 8
        out, diag = fountain.volume_decode(_all_source_symbols(vs, enc), vs)
        assert out == data and len(out) == n_bytes
    # overflow: 2 pages x 16 symbols x S bits max
    smax = fountain.VolumeSpec(n_pages=2, data_len_bytes=1, seed=SMALL_SEED,
                               ldpc_rate_id="r0550",
                               compose_spec=cs).symbol_bits
    too_big = fountain.VolumeSpec(n_pages=2, data_len_bytes=(33 * smax) // 8,
                                  seed=SMALL_SEED, ldpc_rate_id="r0550",
                                  compose_spec=cs)
    try:
        fountain.volume_geometry(too_big)
        raise AssertionError("capacity overflow must raise")
    except ValueError:
        pass
    for bad in (dict(n_pages=0), dict(data_len_bytes=0), dict(seed=b""),
                dict(ldpc_rate_id="r9999"), dict(n_pages=20_000)):
        kw = dict(n_pages=2, data_len_bytes=100, seed=SMALL_SEED,
                  ldpc_rate_id="r0550", compose_spec=cs)
        kw.update(bad)
        try:
            fountain.VolumeSpec(**kw)
            raise AssertionError(f"VolumeSpec must reject {bad}")
        except ValueError:
            pass
    print("  odd sizes 1/100/5227 bytes exact; overflow + bad specs raise")


def test_overhead_curve_k512() -> None:
    """Random-erasure overhead at K = 512 (one block): receive K+delta
    symbols drawn uniformly from a 2048-symbol pool (source + repair mix);
    success = full GE rank. Dense-RLF theory: ~29% at K, then
    prod_{i>delta}(1 - 2^-i) — measured (seeded, deterministic):
    59/200, 155/200, 195/200, 200/200."""
    cs = _small_cspec()
    probe = fountain.VolumeSpec(n_pages=128, data_len_bytes=1,
                                seed=b"paper-store/test-fountain-curve",
                                ldpc_rate_id="r0550", compose_spec=cs)
    vs = fountain.VolumeSpec(n_pages=128,
                             data_len_bytes=64 * probe.symbol_bits,
                             seed=b"paper-store/test-fountain-curve",
                             ldpc_rate_id="r0550", compose_spec=cs)
    k = vs.k_total
    assert k == 512 and vs.n_blocks == 1
    pool_n = vs.n_symbols_total
    assert pool_n == 2048
    pool = fountain._pack_bits_2d(np.stack(
        [fountain.generator_row(vs, 0, i) for i in range(pool_n)]))
    g = rng(vs.seed, b"curve-trials")
    n_trials = 200
    measured = {}
    for delta in (0, 2, 5, 16):
        wins = 0
        for _ in range(n_trials):
            idx = np.sort(g.choice(pool_n, size=k + delta, replace=False))
            rows = pool[idx].copy()
            vals = np.zeros((rows.shape[0], 1), dtype="<u8")
            _, solved = fountain._ge_solve_gf2(rows, vals, k)
            wins += solved is not None
        measured[delta] = wins
    assert 0.17 <= measured[0] / n_trials <= 0.45      # theory 0.289
    assert measured[2] / n_trials >= 0.68              # theory 0.770
    assert measured[5] / n_trials >= 0.92              # theory 0.969
    assert measured[16] == n_trials                    # P(fail) ~ 2^-17
    print("  overhead curve K=512: " + ", ".join(
        f"K+{d}: {w}/{n_trials} = {w / n_trials:.3f}"
        for d, w in measured.items()))


def test_ge_speed_k4096() -> None:
    """Bit-packed GE at K = 4096, one block, adversarial mix (2000 source
    symbols erased -> ~2000 dense repair rows in the system): exact decode;
    reports symbols/s (measured ~5000/s on the dev machine)."""
    cs = _small_cspec()
    seed = b"paper-store/test-fountain-ge4096"
    probe = fountain.VolumeSpec(n_pages=512, data_len_bytes=1, seed=seed,
                                ldpc_rate_id="r0550", compose_spec=cs)
    vs = fountain.VolumeSpec(n_pages=512,
                             data_len_bytes=512 * probe.symbol_bits,
                             seed=seed, ldpc_rate_id="r0550",
                             compose_spec=cs)
    k = vs.k_total
    assert k == 4096 and vs.n_blocks == 1
    data = rng(seed, b"data").integers(0, 256, vs.data_len_bytes,
                                       dtype=np.uint8).tobytes()
    enc = fountain.volume_encode(data, vs)
    g = rng(seed, b"pick")
    drop = set(map(int, g.choice(k, size=2000, replace=False)))
    syms = {(0, t): enc.symbol(0, t) for t in range(k) if t not in drop}
    syms.update({(0, t): enc.symbol(0, t)
                 for t in range(k, k + 2016)})
    t0 = time.perf_counter()
    out, diag = fountain.volume_decode(syms, vs)
    dt = time.perf_counter() - t0
    d0 = diag["blocks"][0]
    assert out == data and d0["rank"] == k and not d0["systematic"]
    print(f"  GE K=4096: {len(syms)} recv (2016 dense), exact in {dt:.2f}s "
          f"= {k / dt:.0f} symbols/s")


if __name__ == "__main__":
    for fn in [test_pack_unpack_bits,
               test_e012_volume_geometry_constants,
               test_esi_bijection_and_source_first,
               test_generator_rows_golden,
               test_encode_framing_agrees_with_ldpc_accounting,
               test_systematic_identity_ge_and_partial,
               test_tiles_to_symbols_certified_only,
               test_data_len_roundtrip_odd_sizes,
               test_overhead_curve_k512,
               test_ge_speed_k4096]:
        print(fn.__name__)
        fn()
    print("all fountain codec tests passed")

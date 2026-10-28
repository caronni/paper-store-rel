"""Preflight for the layout_version-3 pilot value layer (p60b6.v3-k18).

Checks, in order: layout invariants (version 3 accepted, sites SHARED with v2
by contract — no pilot-sites-v3 label) -> value-keystream label separation
(v3 != v2, plane-labeled) -> counter pack/unpack inverse + PAD-BIT rejects ->
counter/address bijection + 2^18 range enforcement (page cap) -> word
round-trip (all planes, random addresses, error injection to t_acq=13) ->
wrong plane / wrong seed / wrong site-phase / cross-format (v2 word under v3
hypothesis and vice versa) rejection -> geometry requirement -> determinism.
The v2 word API must remain byte-identical (tests/test_pilots_v2.py +
tests/test_format_v2_golden.py cover it; a spot check here guards the split).

Runs under pytest, or standalone:  python tests/test_pilots_v3.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from paperholo import bch, pilots
from paperholo.modulation import rng

SEED = b"paper-store/test-pilots-v3"
L2 = pilots.PilotLayout()
L3 = pilots.PilotLayout(version=3)
GEO = {"tiles_x": 25, "tiles_per_page": 925}   # e012-class page geometry
PAGE_CAP = ((1 << 18) - 1) // 925              # 283 for 925-tile pages


def _rand_address(gen: np.random.Generator) -> tuple[str, int, int, int]:
    plane = "KCMY"[int(gen.integers(4))]
    return (
        plane,
        int(gen.integers(200)),      # nominal page range (contract: 200)
        int(gen.integers(37)),
        int(gen.integers(25)),
    )


def test_layout_v3_invariants():
    assert L3.version == 3
    assert L3.period_cells == 60 and L3.block_cells == 6
    assert L3.sites_per_tile == 100 == bch.N_SHORT
    # version 4 exists since the color channel (2026-07-10, COLOR-DESIGN);
    # the next UNDEFINED version must still be rejected
    try:
        pilots.PilotLayout(version=5)
        raise AssertionError("version 5 must be rejected")
    except ValueError:
        pass
    # code + t_acq dispatch
    assert pilots.code_for_layout(L2) is bch.CODE_V2
    assert pilots.code_for_layout(L3) is bch.CODE_V3
    assert pilots.t_acq_for_layout(L2) == 8
    assert pilots.t_acq_for_layout(L3) == 13
    # sites are SHARED with v2 (contract: no pilot-sites-v3 label)
    assert np.array_equal(pilots.site_positions_tile(L3, SEED),
                          pilots.site_positions_tile(L2, SEED))
    assert np.array_equal(pilots.pilot_site_mask((120, 60), L3, SEED),
                          pilots.pilot_site_mask((120, 60), L2, SEED))


def test_value_keystream_v3():
    streams = {}
    for plane in "KCMY":
        ks = pilots.value_keystream_tile(L3, SEED, plane)
        assert ks.shape == (100,) and ks.dtype == np.uint8
        assert np.isin(ks, (0, 1)).all()
        # v3 label != v2 label: the value layer alone identifies the format
        assert not np.array_equal(
            ks, pilots.value_keystream_tile(L2, SEED, plane)), plane
        streams[plane] = ks
    for a in "KCMY":
        for b in "KCMY":
            if a < b:
                assert not np.array_equal(streams[a], streams[b]), (a, b)
    assert not np.array_equal(
        streams["K"], pilots.value_keystream_tile(L3, b"other-seed", "K"))


def test_counter_pack_unpack_and_pad_rejects():
    gen = rng(SEED, b"pack")
    for _ in range(200):
        c = int(gen.integers(1 << 18))
        bits = pilots.pack_counter(c)
        assert bits.shape == (23,) and bits.dtype == np.uint8
        assert not bits[18:].any(), "pad bits must be zero"
        assert pilots.unpack_counter(bits) == c
        # ANY nonzero pad bit must reject (decoder pad gate)
        for pad in range(18, 23):
            bad = bits.copy()
            bad[pad] ^= 1
            assert pilots.unpack_counter(bad) is None, (c, pad)
    # MSB-first spot check: c=1 -> bit 17 set (18-bit field), pads clear
    bits = pilots.pack_counter(1)
    assert bits.sum() == 1 and bits[17] == 1
    for bad_c in (-1, 1 << 18):
        try:
            pilots.pack_counter(bad_c)
            raise AssertionError("out-of-range counter must be rejected")
        except ValueError:
            pass


def test_counter_address_bijection_and_page_cap():
    gen = rng(SEED, b"addr")
    for _ in range(300):
        page = int(gen.integers(PAGE_CAP))
        ty = int(gen.integers(37))
        tx = int(gen.integers(25))
        c = pilots.counter_from_address(page, ty, tx, **GEO)
        assert c == page * 925 + ty * 25 + tx
        assert pilots.address_from_counter(c, **GEO) == (page, ty, tx)
    # page cap: last fully-addressable page for 925-tile pages is 282
    # ((2^18-1)//925 = 283 is only PARTIALLY addressable: 283*925+924 >= 2^18)
    assert pilots.counter_from_address(282, 36, 24, **GEO) == 282 * 925 + 924
    pilots.counter_from_address(283, 0, 0, **GEO)  # still in range
    for bad in [
        lambda: pilots.counter_from_address(283, 36, 24, **GEO),  # > 2^18-1
        lambda: pilots.counter_from_address(-1, 0, 0, **GEO),
        lambda: pilots.counter_from_address(0, 37, 0, **GEO),
        lambda: pilots.counter_from_address(0, 0, 25, **GEO),
        lambda: pilots.counter_from_address(0, 0, 0, tiles_x=25,
                                            tiles_per_page=924),  # not mult
    ]:
        try:
            bad()
            raise AssertionError("out-of-range address must be rejected")
        except ValueError:
            pass


def test_word_roundtrip_v3():
    gen = rng(SEED, b"roundtrip")
    for trial in range(40):
        plane, page, ty, tx = _rand_address(gen)
        word = pilots.encode_word(L3, SEED, plane, page, ty, tx, **GEO)
        assert word.shape == (100,) and word.dtype == np.uint8
        info = pilots.decode_word(word, L3, SEED, plane, max_errors=13, **GEO)
        assert info is not None, trial
        assert info["n_errors"] == 0
        assert (info["page"], info["ptile_y"], info["ptile_x"]) == (page, ty, tx)
        assert info["counter"] == page * 925 + ty * 25 + tx
        assert "plane_id" not in info and "layout_version" not in info
        # survives up to t_acq = t_full = 13 errors, reports the count
        n_flip = int(gen.integers(1, 14))
        pos = gen.permutation(100)[:n_flip]
        noisy = word.copy()
        noisy[pos] ^= 1
        info2 = pilots.decode_word(noisy, L3, SEED, plane, max_errors=13, **GEO)
        assert info2 is not None and info2["n_errors"] == n_flip
        assert (info2["page"], info2["ptile_y"], info2["ptile_x"]) == (page, ty, tx)


def test_wrong_context_rejects_v3():
    """Wrong plane / wrong seed / wrong site-phase / wrong FORMAT hypothesis:
    the word is a random point w.r.t. the hypothesis keystream, so acceptance
    ~ the (100,23) t=13 false-accept rate (~1.7e-9 incl. pad gate). Gate at
    >= 99% rejection."""
    gen = rng(SEED, b"wrong-ctx")
    n_trials = 200
    for kind in ("plane", "seed", "phase", "v2-under-v3", "v3-under-v2"):
        n_reject = 0
        for _ in range(n_trials):
            plane, page, ty, tx = _rand_address(gen)
            if kind == "v2-under-v3":
                word = pilots.encode_word(L2, SEED, plane, page, ty, tx)
                res = pilots.decode_word(word, L3, SEED, plane,
                                         max_errors=13, **GEO)
            elif kind == "v3-under-v2":
                word = pilots.encode_word(L3, SEED, plane, page, ty, tx, **GEO)
                res = pilots.decode_word(word, L2, SEED, plane, max_errors=8)
            else:
                word = pilots.encode_word(L3, SEED, plane, page, ty, tx, **GEO)
                if kind == "plane":
                    other = "KCMY"[(("KCMY".index(plane)) + 1
                                    + int(gen.integers(3))) % 4]
                    res = pilots.decode_word(word, L3, SEED, other,
                                             max_errors=13, **GEO)
                elif kind == "seed":
                    res = pilots.decode_word(word, L3, b"wrong-seed", plane,
                                             max_errors=13, **GEO)
                else:  # wrong site phase = cyclic shift
                    shift = int(gen.integers(1, 100))
                    res = pilots.decode_word(np.roll(word, shift), L3, SEED,
                                             plane, max_errors=13, **GEO)
            if res is None:
                n_reject += 1
        assert n_reject >= 0.99 * n_trials, (kind, n_reject)


def test_geometry_required_for_v3():
    for bad in [
        lambda: pilots.encode_word(L3, SEED, "K", 0, 0, 0),
        lambda: pilots.encode_word(L3, SEED, "K", 0, 0, 0, tiles_x=25),
        lambda: pilots.decode_word(np.zeros(100, np.uint8), L3, SEED, "K", 13),
    ]:
        try:
            bad()
            raise AssertionError("v3 without geometry must be rejected")
        except ValueError:
            pass
    # v2 path ignores geometry kwargs (uniform call sites)
    a = pilots.encode_word(L2, SEED, "K", 0, 1, 2)
    b = pilots.encode_word(L2, SEED, "K", 0, 1, 2, **GEO)
    assert np.array_equal(a, b)


def test_coordinate_code_wrapper_v3():
    word = pilots.encode_word(L3, SEED, "M", 5, 3, 9, **GEO)
    assert np.array_equal(
        pilots.coordinate_code(L3, SEED, "M", 5, 3, 9, **GEO), word)
    assert pilots.expected_word_bits is pilots.encode_word  # one implementation


def test_determinism_v3():
    w_a = pilots.encode_word(L3, SEED, "C", 100, 7, 13, **GEO)
    w_b = pilots.encode_word(pilots.PilotLayout(version=3), SEED, "C",
                             100, 7, 13, **GEO)
    assert np.array_equal(w_a, w_b)
    assert not np.array_equal(
        w_a, pilots.encode_word(L3, SEED, "C", 100, 7, 14, **GEO))
    # adjacent-counter words differ (the Stage-B neighbor prediction rests
    # on distinct per-tile codewords, c+1 / c+tiles_x)
    right = pilots.encode_word(L3, SEED, "C", 100, 7, 14, **GEO)
    below = pilots.encode_word(L3, SEED, "C", 100, 8, 13, **GEO)
    assert not np.array_equal(right, below)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")

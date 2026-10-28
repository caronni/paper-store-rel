"""Preflight for the layout_version-2 pilot lattice + window code (p60b6.v2).

Checks, in order: layout invariants -> exact 1/36 density + tiling periodicity
on multiple-of-60 grids -> v1/v2 label separation -> site raster order ->
value-keystream separation -> pack/unpack inverse (MSB-first) -> word
round-trip (all planes, random addresses, error injection to t_acq) -> wrong
plane / wrong seed / wrong site-phase rejection -> coordinate_code wrapper ->
determinism. The v1 pilot_sites pattern must remain byte-untouched
(test_roundtrip_sim.py covers it; a spot check here guards the label split).

Runs under pytest, or standalone:  python tests/test_pilots_v2.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from paperholo import bch, pilots
from paperholo.modulation import rng

SEED = b"paper-store/test-pilots-v2"
LAYOUT = pilots.PilotLayout()


def _rand_address(gen: np.random.Generator) -> tuple[str, int, int, int]:
    plane = "KCMY"[int(gen.integers(4))]
    return (
        plane,
        int(gen.integers(1 << 18)),
        int(gen.integers(64)),
        int(gen.integers(64)),
    )


def test_layout_invariants():
    assert LAYOUT.period_cells == 60 and LAYOUT.block_cells == 6
    assert LAYOUT.blocks_per_period == 10
    assert LAYOUT.sites_per_tile == 100 == bch.N_SHORT
    assert LAYOUT.density == 1.0 / 36.0
    try:
        pilots.PilotLayout(period_cells=64, block_cells=6)  # the v1 bug
        raise AssertionError("indivisible period must be rejected")
    except ValueError:
        pass
    try:
        pilots.PilotLayout(version=1)
        raise AssertionError("version != 2 must be rejected")
    except ValueError:
        pass


def test_density_and_periodicity():
    for shape in [(60, 60), (120, 180), (300, 240)]:
        m = pilots.pilot_site_mask(shape, LAYOUT, SEED)
        assert m.shape == shape and m.dtype == bool
        n_tiles = (shape[0] // 60) * (shape[1] // 60)
        assert int(m.sum()) == 100 * n_tiles  # density exactly 100/3600
        assert m.mean() == 1.0 / 36.0
    big = pilots.pilot_site_mask((180, 120), LAYOUT, SEED)
    tile = big[:60, :60]
    for ty in range(3):
        for tx in range(2):
            assert np.array_equal(big[ty * 60 : ty * 60 + 60, tx * 60 : tx * 60 + 60], tile)
    try:
        pilots.pilot_site_mask((90, 120), LAYOUT, SEED)
        raise AssertionError("non-multiple-of-60 shape must be rejected")
    except ValueError:
        pass


def test_v1_v2_label_separation():
    """Same seed, different derivation labels: masks must differ, and v1 must
    keep its known (buggy) 2.44% density while v2 is exactly 1/36."""
    shape = (960, 960)  # multiple of both 60 and 64
    m_v1 = pilots.pilot_sites(shape, SEED)
    m_v2 = pilots.pilot_site_mask(shape, LAYOUT, SEED)
    assert not np.array_equal(m_v1, m_v2)
    assert abs(m_v1.mean() - 100.0 / 64**2) < 1e-12  # v1 stays frozen (2.44%)
    assert m_v2.mean() == 1.0 / 36.0


def test_site_positions_raster_order():
    pos = pilots.site_positions_tile(LAYOUT, SEED)
    assert pos.shape == (100, 2)
    for s in range(100):
        by, bx = s // 10, s % 10
        y_cell, x_cell = int(pos[s, 0]), int(pos[s, 1])
        assert by * 6 <= y_cell < (by + 1) * 6, s
        assert bx * 6 <= x_cell < (bx + 1) * 6, s
    # positions and mask agree
    m = pilots.pilot_site_mask((60, 60), LAYOUT, SEED)
    from_pos = np.zeros((60, 60), dtype=bool)
    from_pos[pos[:, 0], pos[:, 1]] = True
    assert np.array_equal(m, from_pos)


def test_value_keystream():
    streams = {}
    for plane in "KCMY":
        ks = pilots.value_keystream_tile(LAYOUT, SEED, plane)
        assert ks.shape == (100,) and ks.dtype == np.uint8
        assert np.isin(ks, (0, 1)).all()
        assert np.array_equal(ks, pilots.value_keystream_tile(LAYOUT, SEED, plane))
        streams[plane] = ks
    for a in "KCMY":
        for b in "KCMY":
            if a < b:
                assert not np.array_equal(streams[a], streams[b]), (a, b)
    assert not np.array_equal(
        streams["K"], pilots.value_keystream_tile(LAYOUT, b"other-seed", "K")
    )
    try:
        pilots.value_keystream_tile(LAYOUT, SEED, "Z")
        raise AssertionError("unknown plane must be rejected")
    except ValueError:
        pass


def test_pack_unpack_inverse():
    gen = rng(SEED, b"pack")
    for _ in range(200):
        plane, page, ty, tx = _rand_address(gen)
        bits = pilots.pack_message(plane, page, ty, tx)
        assert bits.shape == (36,) and bits.dtype == np.uint8
        info = pilots.unpack_message(bits)
        assert info == {
            "layout_version": 2,
            "plane_id": pilots.PLANE_ID[plane],
            "page": page,
            "ptile_y": ty,
            "ptile_x": tx,
        }
    # MSB-first spot check: layout_version=2 -> first 4 bits 0010; K -> 00
    bits = pilots.pack_message("K", 0, 0, 0)
    assert list(bits[:6]) == [0, 0, 1, 0, 0, 0]
    assert bits.sum() == 1
    # field range validation
    for bad in [
        lambda: pilots.pack_message("K", 1 << 18, 0, 0),
        lambda: pilots.pack_message("K", 0, 64, 0),
        lambda: pilots.pack_message("K", 0, 0, -1),
        lambda: pilots.pack_message("Q", 0, 0, 0),
        lambda: pilots.pack_message("K", 0, 0, 0, layout_version=16),
    ]:
        try:
            bad()
            raise AssertionError("out-of-range field must be rejected")
        except ValueError:
            pass


def test_word_roundtrip():
    gen = rng(SEED, b"roundtrip")
    for trial in range(40):
        plane, page, ty, tx = _rand_address(gen)
        word = pilots.encode_word(LAYOUT, SEED, plane, page, ty, tx)
        assert word.shape == (100,) and word.dtype == np.uint8
        info = pilots.decode_word(word, LAYOUT, SEED, plane, max_errors=8)
        assert info is not None, trial
        assert info["n_errors"] == 0
        assert (info["plane_id"], info["page"], info["ptile_y"], info["ptile_x"]) == (
            pilots.PLANE_ID[plane],
            page,
            ty,
            tx,
        )
        assert info["layout_version"] == 2
        # survives up to t_acq errors, reports the count
        n_flip = int(gen.integers(1, 9))
        pos = gen.permutation(100)[:n_flip]
        noisy = word.copy()
        noisy[pos] ^= 1
        info2 = pilots.decode_word(noisy, LAYOUT, SEED, plane, max_errors=8)
        assert info2 is not None and info2["n_errors"] == n_flip
        assert info2["page"] == page and info2["ptile_y"] == ty and info2["ptile_x"] == tx


def test_wrong_context_rejects():
    """Wrong plane / wrong seed / wrong site-phase descramble: the word is a
    random point w.r.t. the hypothesis, so acceptance ~ the BCH false-accept
    rate (~2.3e-8). Gate at >= 99% rejection per the contract."""
    gen = rng(SEED, b"wrong-ctx")
    n_trials = 200
    for kind in ("plane", "seed", "phase"):
        n_reject = 0
        for _ in range(n_trials):
            plane, page, ty, tx = _rand_address(gen)
            word = pilots.encode_word(LAYOUT, SEED, plane, page, ty, tx)
            if kind == "plane":
                other = "KCMY"[(("KCMY".index(plane)) + 1 + int(gen.integers(3))) % 4]
                res = pilots.decode_word(word, LAYOUT, SEED, other, max_errors=8)
            elif kind == "seed":
                res = pilots.decode_word(word, LAYOUT, b"wrong-seed", plane, max_errors=8)
            else:  # wrong site phase: bit/site misassignment = cyclic shift
                shift = int(gen.integers(1, 100))
                res = pilots.decode_word(np.roll(word, shift), LAYOUT, SEED, plane, max_errors=8)
            if res is None:
                n_reject += 1
        assert n_reject >= 0.99 * n_trials, (kind, n_reject)


def test_coordinate_code_wrapper_and_alias():
    gen = rng(SEED, b"wrapper")
    plane, page, ty, tx = _rand_address(gen)
    word = pilots.encode_word(LAYOUT, SEED, plane, page, ty, tx)
    assert np.array_equal(pilots.coordinate_code(LAYOUT, SEED, plane, page, ty, tx), word)
    assert pilots.expected_word_bits is pilots.encode_word  # one implementation


def test_determinism():
    pos_a = pilots.site_positions_tile(LAYOUT, SEED)
    pos_b = pilots.site_positions_tile(pilots.PilotLayout(), SEED)
    assert np.array_equal(pos_a, pos_b)
    m_a = pilots.pilot_site_mask((120, 120), LAYOUT, SEED)
    m_b = pilots.pilot_site_mask((120, 120), LAYOUT, SEED)
    assert np.array_equal(m_a, m_b)
    w_a = pilots.encode_word(LAYOUT, SEED, "C", 12345, 7, 13)
    w_b = pilots.encode_word(LAYOUT, SEED, "C", 12345, 7, 13)
    assert np.array_equal(w_a, w_b)
    assert not np.array_equal(w_a, pilots.encode_word(LAYOUT, SEED, "C", 12345, 7, 14))


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")

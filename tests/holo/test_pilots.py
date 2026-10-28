"""format/pilots: exact-100 quota construction + address words.

GOLDEN (bump-don't-edit): the site-pattern digest pins the v1 family
lattice — a mismatch is a format fork.
"""
import hashlib

import numpy as np


from holo.core import bch
from holo.format import pilots

FAMILY = b"holo/v1/sites/p100"
ROW = b"holo/v1/c2-r0550/3328x2304"

GOLDEN_SITES_P100 = ("bdc8747a748669fe226cda7967c544ee"
                     "4cc7fc62ce69d63f26839fdffd823506")


def test_exact_100_one_per_quota_cell():
    cells = pilots.word_site_cells_yx(FAMILY)
    assert cells.shape == (100, 2)
    edges = pilots._QUOTA_EDGES
    for q in range(100):
        qi, qj = q // 10, q % 10
        y, x = cells[q]
        assert edges[qi] <= y < edges[qi + 1]
        assert edges[qj] <= x < edges[qj + 1]
    flat = cells[:, 0] * 64 + cells[:, 1]
    assert np.unique(flat).size == 100


def test_site_pattern_golden_and_deterministic():
    a = pilots.word_site_cells_yx(FAMILY)
    b = pilots.word_site_cells_yx(FAMILY)
    assert np.array_equal(a, b)
    digest = hashlib.sha256(a.astype(np.int64).tobytes()).hexdigest()
    assert digest == GOLDEN_SITES_P100
    other = pilots.word_site_cells_yx(b"holo/v1/sites/p128")
    assert not np.array_equal(a, other)


def test_site_cell_indices_sorted_unique():
    flat = pilots.site_cell_indices(FAMILY)
    assert flat.shape == (100,)
    assert np.all(np.diff(flat) > 0)
    assert flat.min() >= 0 and flat.max() < 4096


def test_filler_sites_collision_free():
    word, filler = pilots.site_cells_yx(FAMILY, n_filler=28)
    assert filler.shape == (28, 2)
    all_flat = np.concatenate([word, filler])[:, 0] * 64 \
        + np.concatenate([word, filler])[:, 1]
    assert np.unique(all_flat).size == 128
    flat = pilots.site_cell_indices(FAMILY, 28)
    assert flat.size == 128


def test_word_round_trip_and_pad_gate():
    for counter in (0, 1, 1871, (1 << 18) - 1):
        vals = pilots.word_values(ROW, [counter])[0]
        assert vals.shape == (100,)
        assert pilots.decode_word(vals, ROW) == counter
    # wrong row seed -> coin flips -> refusal
    assert pilots.decode_word(pilots.word_values(ROW, [7])[0],
                              b"holo/v1/c3-r0550/2240x1536") is None
    # nonzero pads -> refusal even when the word decodes
    msg = np.zeros(23, dtype=np.uint8)
    msg[22] = 1  # a pad bit
    bad = bch.encode(msg) ^ pilots.value_scramble_bits(ROW)
    assert pilots.decode_word(bad, ROW) is None


def test_word_error_and_erasure_tolerance():
    vals = pilots.word_values(ROW, [12345])[0]
    rng = np.random.default_rng(5)
    noisy = vals.copy()
    noisy[rng.choice(100, 13, replace=False)] ^= 1
    assert pilots.decode_word(noisy, ROW) == 12345
    era_idx = rng.choice(100, 20, replace=False)
    erased = vals.copy()
    erased[era_idx] = 0
    assert pilots.decode_word(erased, ROW, erasure_idx=era_idx) == 12345


def test_counter_out_of_range_refused():
    import pytest
    with pytest.raises(ValueError):
        pilots.encode_word(1 << 18)

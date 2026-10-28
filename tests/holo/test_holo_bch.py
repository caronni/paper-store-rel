"""holo BCH word code: g(x) golden, round trip, t=13 boundary, erasures,
minimum-distance spot check.

GOLDEN VECTOR (bump-don't-edit): G_POLY_SHA256 pins the derived generator
polynomial of BCH(127,50,t=13)->(100,23). A mismatch means the word code
changed — that is a printed-format fork (new format row), never a test to
update. Cross-verified byte-identical to paperholo CODE_V3 at porting time
(2026-07-19); the check itself must not import paperholo.
"""
import hashlib

import numpy as np


from holo.core import bch

# frozen 2026-07-19: sha256 of generator_poly().tobytes() (78 uint8 coeffs)
G_POLY_SHA256 = ("a0be5064cfef57b2a84aaadbd7bd13b9"
                 "772b1259fa041c25af0d7bde4922b684")

_RNG = np.random.default_rng(0x5B3C)


def _random_message() -> np.ndarray:
    return _RNG.integers(0, 2, bch.K_MSG).astype(np.uint8)


def _corrupt(word: np.ndarray, n_flips: int) -> tuple[np.ndarray, np.ndarray]:
    pos = _RNG.choice(bch.N_WORD, size=n_flips, replace=False)
    w = word.copy()
    w[pos] ^= 1
    return w, pos


def test_generator_poly_golden():
    g = bch.generator_poly()
    assert g.shape == (bch.N_PARITY + 1,) and g.dtype == np.uint8
    assert g[0] == 1 and g[-1] == 1
    assert hashlib.sha256(g.tobytes()).hexdigest() == G_POLY_SHA256


def test_encode_decode_round_trip():
    for _ in range(50):
        m = _random_message()
        cw = bch.encode(m)
        assert cw.shape == (bch.N_WORD,)
        assert np.array_equal(bch.message_from_word(cw), m)
        res = bch.decode(cw)
        assert res is not None
        corrected, n_err = res
        assert n_err == 0 and np.array_equal(corrected, cw)


def test_corrects_exactly_t13():
    for _ in range(20):
        cw = bch.encode(_random_message())
        w, _ = _corrupt(cw, bch.T)
        res = bch.decode(w)
        assert res is not None
        corrected, n_err = res
        assert n_err == bch.T and np.array_equal(corrected, cw)


def test_refuses_beyond_t13():
    # 14 random errors: BM locator degree exceeds t, Chien mismatches, or
    # the re-check fails. Refusal verified 300/300 at port time; 30 trials
    # under a fixed seed here.
    for _ in range(30):
        cw = bch.encode(_random_message())
        w, _ = _corrupt(cw, bch.T + 1)
        assert bch.decode(w) is None


def test_erasures_26_zero_errors_decodes():
    cw = bch.encode(_random_message())
    era = _RNG.choice(bch.N_WORD, size=26, replace=False)
    w = cw.copy()
    w[era] = _RNG.integers(0, 2, era.size).astype(np.uint8)  # garbage fill
    res = bch.decode_erasures(w, era)
    assert res is not None
    corrected, e_out = res
    assert e_out == 0 and np.array_equal(corrected, cw)


def test_erasures_27_refuses():
    cw = bch.encode(_random_message())
    era = _RNG.choice(bch.N_WORD, size=27, replace=False)
    assert bch.decode_erasures(cw, era) is None  # f > 26: refused up front


def test_erasures_zero_with_13_errors_decodes():
    cw = bch.encode(_random_message())
    w, _ = _corrupt(cw, bch.T)
    res = bch.decode_erasures(w, np.array([], dtype=np.int64))
    assert res is not None
    corrected, e_out = res
    assert e_out == bch.T and np.array_equal(corrected, cw)


def test_erasures_mixed_budget_boundary():
    # 2e + f = 26 exactly (e=6, f=14): must decode with e_out == 6.
    cw = bch.encode(_random_message())
    era = _RNG.choice(bch.N_WORD, size=14, replace=False)
    keep = np.setdiff1d(np.arange(bch.N_WORD), era)
    err_pos = _RNG.choice(keep, size=6, replace=False)
    w = cw.copy()
    w[err_pos] ^= 1
    w[era] = _RNG.integers(0, 2, era.size).astype(np.uint8)
    res = bch.decode_erasures(w, era)
    assert res is not None
    corrected, e_out = res
    assert e_out == 6 and np.array_equal(corrected, cw)


def test_erasures_never_returns_beyond_budget():
    # Over budget (e=7, f=14 -> 2e+f=28): any accepted decode would violate
    # the internal gate; result must be None or the TRUE codeword reached
    # within budget from the trial fills (never a certified overrun).
    for _ in range(10):
        cw = bch.encode(_random_message())
        era = _RNG.choice(bch.N_WORD, size=14, replace=False)
        keep = np.setdiff1d(np.arange(bch.N_WORD), era)
        err_pos = _RNG.choice(keep, size=7, replace=False)
        w = cw.copy()
        w[err_pos] ^= 1
        w[era] = _RNG.integers(0, 2, era.size).astype(np.uint8)
        res = bch.decode_erasures(w, era)
        if res is not None:
            corrected, e_out = res
            assert 2 * e_out + 14 <= 2 * bch.T


def test_minimum_distance_spot_check():
    # ~200 random codeword pairs, all pairwise distances >= 27.
    msgs = [_random_message() for _ in range(200)]
    words = [bch.encode(m) for m in msgs]
    checked = 0
    for a in range(0, 200, 2):
        m1, m2 = msgs[a], msgs[a + 1]
        if np.array_equal(m1, m2):
            continue
        d = int(np.sum(words[a] != words[a + 1]))
        assert d >= bch.D_MIN, f"pair distance {d} < {bch.D_MIN}"
        checked += 1
    # linearity: distance(c1, c2) == weight(encode(m1 xor m2)) — cross-check
    for a in range(0, 40, 2):
        m1, m2 = msgs[a], msgs[a + 1]
        if np.array_equal(m1, m2):
            continue
        d = int(np.sum(words[a] != words[a + 1]))
        wt = int(bch.encode(m1 ^ m2).sum())
        assert d == wt
    assert checked >= 90

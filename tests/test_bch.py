"""Preflight for the pilot window codes: BCH(127,64,t=10)->(100,37)
(layout_version 2) and BCH(127,50,t=13)->(100,23) (layout_version 3).

v2 checks, in order: generator algebra -> encode/decode identity -> exhaustive
single+double errors -> random weights 1..10 -> beyond-radius behavior
(weight 11..14: None or a DIFFERENT valid codeword, never silence) ->
acquisition-radius rejection (t_acq=8 vs weight-9+) -> random-word
false-accept rate at t_acq=8 (< 1e-3; contract estimate ~2.3e-8) ->
shortened-position rejection -> vectorized-API consistency -> determinism ->
dmin soft check (no codeword of weight < 21 in 1e4 random messages).

v3 checks mirror the v2 gates on bch.CODE_V3 (t=13, d>=27): generator deg 77,
weights 1..13 corrected, 14..17 rejected-or-miscorrected-never-silent,
random-word false-accept at t=13 measured and reported, shortened-position
rejects, vectorized consistency, dmin soft check >= 27, and v2/v3 codeword
cross-rejection.

Runs under pytest, or standalone:  python tests/test_bch.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from paperholo import bch
from paperholo.modulation import rng

SEED = b"paper-store/test-bch"


def _rand_message(gen: np.random.Generator) -> np.ndarray:
    return gen.integers(0, 2, size=bch.K_SHORT).astype(np.uint8)


def _polymod2(a: int, g: int) -> int:
    gd = g.bit_length() - 1
    while a.bit_length() - 1 >= gd and a:
        a ^= g << (a.bit_length() - 1 - gd)
    return a


def test_generator_poly():
    g = bch.generator_poly()
    assert g.shape == (64,) and g.dtype == np.uint8
    assert g[63] == 1 and g[0] == 1, "g must have degree exactly 63, g(0) != 0"
    assert np.isin(g, (0, 1)).all()
    g_int = sum(int(c) << i for i, c in enumerate(g))
    assert _polymod2((1 << 127) | 1, g_int) == 0, "g(x) must divide x^127 - 1"


def test_encode_decode_identity():
    gen = rng(SEED, b"identity")
    msgs = [np.zeros(bch.K_SHORT, np.uint8), np.ones(bch.K_SHORT, np.uint8)]
    msgs += [_rand_message(gen) for _ in range(50)]
    for m in msgs:
        cw = bch.encode(m)
        assert cw.shape == (bch.N_SHORT,) and cw.dtype == np.uint8
        assert np.array_equal(bch.message_from_word(cw), m)  # systematic
        assert not bch.syndromes(cw).any()
        res = bch.decode(cw, bch.T_FULL)
        assert res is not None
        corrected, n_err = res
        assert n_err == 0 and np.array_equal(corrected, cw)


def test_all_single_and_double_errors():
    gen = rng(SEED, b"exhaustive")
    cw = bch.encode(_rand_message(gen))
    for i in range(bch.N_SHORT):
        word = cw.copy()
        word[i] ^= 1
        res = bch.decode(word, bch.T_FULL)
        assert res is not None and res[1] == 1 and np.array_equal(res[0], cw), i
    for i in range(bch.N_SHORT):
        for j in range(i + 1, bch.N_SHORT):
            word = cw.copy()
            word[i] ^= 1
            word[j] ^= 1
            res = bch.decode(word, bch.T_FULL)
            assert res is not None and res[1] == 2, (i, j)
            assert np.array_equal(res[0], cw), (i, j)


def test_random_errors_weights_1_to_10():
    gen = rng(SEED, b"weights")
    pool = [bch.encode(_rand_message(gen)) for _ in range(100)]
    n_trials = 2000
    for w in range(1, bch.T_FULL + 1):
        for _ in range(n_trials):
            cw = pool[int(gen.integers(len(pool)))]
            pos = gen.permutation(bch.N_SHORT)[:w]
            word = cw.copy()
            word[pos] ^= 1
            res = bch.decode(word, bch.T_FULL)
            assert res is not None, w
            corrected, n_err = res
            assert n_err == w and np.array_equal(corrected, cw), w


def test_beyond_radius_weights_11_to_14():
    """Miscorrection to another codeword is allowed; a silent wrong answer or
    a non-codeword output is not."""
    gen = rng(SEED, b"beyond")
    n_trials = 400
    n_none = 0
    for w in range(11, 15):
        for _ in range(n_trials):
            cw = bch.encode(_rand_message(gen))
            pos = gen.permutation(bch.N_SHORT)[:w]
            word = cw.copy()
            word[pos] ^= 1
            res = bch.decode(word, bch.T_FULL)
            if res is None:
                n_none += 1
                continue
            corrected, n_err = res
            assert not bch.syndromes(corrected).any(), "output must be a codeword"
            assert not np.array_equal(corrected, cw), "cannot equal transmitted"
            assert 0 < n_err <= bch.T_FULL
    assert n_none > 0  # dmin 21 makes decode-to-anything rare; most must reject


def test_acquisition_radius_rejects_weight_9_plus():
    """t_acq=8: weight 9..12 errors sit > 8 from transmitted and (dmin 21)
    > 8 from every other codeword, so rejection is expected ~always."""
    gen = rng(SEED, b"t-acq")
    n_trials, t_acq = 2000, 8
    n_none = 0
    for _ in range(n_trials):
        cw = bch.encode(_rand_message(gen))
        w = int(gen.integers(9, 13))
        pos = gen.permutation(bch.N_SHORT)[:w]
        word = cw.copy()
        word[pos] ^= 1
        if bch.decode(word, t_acq) is None:
            n_none += 1
    assert n_none >= 0.99 * n_trials, f"only {n_none}/{n_trials} rejected"


def test_random_word_false_accept_rate():
    gen = rng(SEED, b"false-accept")
    n_trials, t_acq = 2000, 8
    words = gen.integers(0, 2, size=(n_trials, bch.N_SHORT)).astype(np.uint8)
    results = bch.decode_many(words, t_acq)
    n_acc = sum(1 for r in results if r is not None)
    rate = n_acc / n_trials
    print(f"  random-word acceptance at t_acq=8: {n_acc}/{n_trials} = {rate:.2e}")
    assert rate < 1e-3, rate  # contract estimate ~2.3e-8: expect ~0


def test_shortened_position_rejection():
    """A full-code codeword with ink in the shortened positions, truncated to
    100 bits, syndromes like errors at positions >= 100 — must reject."""
    g_int = sum(int(c) << i for i, c in enumerate(bch.generator_poly()))
    # full 64-bit message with bits j in {37, 40, 50} -> positions 100, 103, 113
    m_int = (1 << 37) | (1 << 40) | (1 << 50)
    shifted = m_int << 63
    full = shifted | _polymod2(shifted, g_int)
    word = np.array([(full >> i) & 1 for i in range(bch.N_SHORT)], dtype=np.uint8)
    assert bch.syndromes(word).any()  # truncation is visible to the syndromes
    assert bch.decode(word, bch.T_FULL) is None
    # mixed: an additional in-word flip must still reject (a root stays >= 100)
    word2 = word.copy()
    word2[10] ^= 1
    assert bch.decode(word2, bch.T_FULL) is None


def test_vectorized_apis_match_scalar():
    gen = rng(SEED, b"vectorized")
    words = []
    for _ in range(64):
        cw = bch.encode(_rand_message(gen))
        w = int(gen.integers(0, 12))
        pos = gen.permutation(bch.N_SHORT)[:w]
        cw = cw.copy()
        cw[pos] ^= 1
        words.append(cw)
    words_arr = np.stack(words)
    synd_many = bch.syndromes_many(words_arr)
    assert synd_many.shape == (64, 20)
    many = bch.decode_many(words_arr, 8)
    for h in range(64):
        assert np.array_equal(synd_many[h], bch.syndromes(words_arr[h]))
        single = bch.decode(words_arr[h], 8)
        if single is None:
            assert many[h] is None
        else:
            assert many[h] is not None
            assert np.array_equal(many[h][0], single[0]) and many[h][1] == single[1]


def test_determinism():
    gen_a = rng(SEED, b"determinism")
    gen_b = rng(SEED, b"determinism")
    m_a, m_b = _rand_message(gen_a), _rand_message(gen_b)
    assert np.array_equal(m_a, m_b)
    assert np.array_equal(bch.encode(m_a), bch.encode(m_b))
    assert np.array_equal(bch.generator_poly(), bch.generator_poly())
    # finding [9]: gf_tables() returns the SAME cached tuple object, so
    # comparing two plain calls is a tautology (it compares an array with
    # itself and cannot fail, even after in-place corruption). Force an
    # independent recomputation by dropping the cache entry.
    exp1, log1 = bch.gf_tables()
    exp1, log1 = exp1.copy(), log1.copy()
    bch._cache.pop("tables", None)
    exp2, log2 = bch.gf_tables()
    assert exp1 is not exp2 and log1 is not log2
    assert np.array_equal(exp1, exp2) and np.array_equal(log1, log2)


def test_dmin_soft_check():
    """No codeword of weight < 21 among 1e4 random nonzero messages
    (designed distance; soft statistical check, not a proof)."""
    gen = rng(SEED, b"dmin")
    min_w = bch.N_SHORT
    for _ in range(10_000):
        m = _rand_message(gen)
        if not m.any():
            continue
        w = int(bch.encode(m).sum())
        min_w = min(min_w, w)
    print(f"  min codeword weight over 1e4 random messages: {min_w}")
    assert min_w >= 21, min_w


# ---------------------------------------------------------------------------
# layout_version-3 code: BCH(127,50,t=13) shortened -> (100,23), d>=27
# ---------------------------------------------------------------------------

C3 = bch.CODE_V3


def _rand_message_v3(gen: np.random.Generator) -> np.ndarray:
    return gen.integers(0, 2, size=C3.k_short).astype(np.uint8)


def test_v3_generator_poly():
    g = C3.generator_poly()
    assert g.shape == (78,) and g.dtype == np.uint8
    assert g[77] == 1 and g[0] == 1, "g must have degree exactly 77, g(0) != 0"
    assert np.isin(g, (0, 1)).all()
    g_int = sum(int(c) << i for i, c in enumerate(g))
    assert _polymod2((1 << 127) | 1, g_int) == 0, "g(x) must divide x^127 - 1"
    # frozen instance parameters
    assert (C3.k_full, C3.t_full, C3.k_short, C3.n_parity) == (50, 13, 23, 77)


def test_v3_encode_decode_identity():
    gen = rng(SEED, b"v3-identity")
    msgs = [np.zeros(C3.k_short, np.uint8), np.ones(C3.k_short, np.uint8)]
    msgs += [_rand_message_v3(gen) for _ in range(50)]
    for m in msgs:
        cw = C3.encode(m)
        assert cw.shape == (C3.n_short,) and cw.dtype == np.uint8
        assert np.array_equal(C3.message_from_word(cw), m)  # systematic
        assert not C3.syndromes(cw).any()
        res = C3.decode(cw, C3.t_full)
        assert res is not None
        corrected, n_err = res
        assert n_err == 0 and np.array_equal(corrected, cw)


def test_v3_random_errors_weights_1_to_13():
    gen = rng(SEED, b"v3-weights")
    pool = [C3.encode(_rand_message_v3(gen)) for _ in range(100)]
    n_trials = 2000
    for w in range(1, C3.t_full + 1):
        for _ in range(n_trials):
            cw = pool[int(gen.integers(len(pool)))]
            pos = gen.permutation(C3.n_short)[:w]
            word = cw.copy()
            word[pos] ^= 1
            res = C3.decode(word, C3.t_full)
            assert res is not None, w
            corrected, n_err = res
            assert n_err == w and np.array_equal(corrected, cw), w


def test_v3_beyond_radius_weights_14_to_17():
    """Miscorrection to another codeword is allowed; a silent wrong answer or
    a non-codeword output is not. d>=27 makes decode-to-anything rare."""
    gen = rng(SEED, b"v3-beyond")
    n_trials = 400
    n_none = 0
    for w in range(14, 18):
        for _ in range(n_trials):
            cw = C3.encode(_rand_message_v3(gen))
            pos = gen.permutation(C3.n_short)[:w]
            word = cw.copy()
            word[pos] ^= 1
            res = C3.decode(word, C3.t_full)
            if res is None:
                n_none += 1
                continue
            corrected, n_err = res
            assert not C3.syndromes(corrected).any(), "output must be a codeword"
            assert not np.array_equal(corrected, cw), "cannot equal transmitted"
            assert 0 < n_err <= C3.t_full
    assert n_none > 0
    print(f"  v3 weight 14..17: {n_none}/{4 * n_trials} rejected")


def test_v3_random_word_false_accept_rate():
    """(100,23) at the FULL t=13 radius (v3 is a single-stage full-strength
    search): analytic FA ~1.7e-9/word incl. the pilots pad gate (contract:
    5.0e-5 per 28,800-hypothesis window); expect 0 accepts here. Any accept
    that does occur must be a valid codeword (never silent garbage)."""
    gen = rng(SEED, b"v3-false-accept")
    n_trials = 2000
    words = gen.integers(0, 2, size=(n_trials, C3.n_short)).astype(np.uint8)
    results = C3.decode_many(words, C3.t_full)
    n_acc = 0
    for r in results:
        if r is None:
            continue
        n_acc += 1
        assert not C3.syndromes(r[0]).any()
    rate = n_acc / n_trials
    print(f"  v3 random-word acceptance at t=13: {n_acc}/{n_trials} = {rate:.2e}")
    assert rate < 1e-3, rate


def test_v3_shortened_position_rejection():
    """A full-code codeword with ink in the shortened positions, truncated to
    100 bits, syndromes like errors at positions >= 100 — must reject."""
    g_int = sum(int(c) << i for i, c in enumerate(C3.generator_poly()))
    # full 50-bit message with bits j in {23, 26, 40} -> positions 100, 103, 117
    m_int = (1 << 23) | (1 << 26) | (1 << 40)
    shifted = m_int << 77
    full = shifted | _polymod2(shifted, g_int)
    word = np.array([(full >> i) & 1 for i in range(C3.n_short)], dtype=np.uint8)
    assert C3.syndromes(word).any()  # truncation is visible to the syndromes
    assert C3.decode(word, C3.t_full) is None
    # mixed: an additional in-word flip must still reject (a root stays >= 100)
    word2 = word.copy()
    word2[10] ^= 1
    assert C3.decode(word2, C3.t_full) is None


def test_v3_vectorized_apis_match_scalar():
    gen = rng(SEED, b"v3-vectorized")
    words = []
    for _ in range(64):
        cw = C3.encode(_rand_message_v3(gen))
        w = int(gen.integers(0, 16))
        pos = gen.permutation(C3.n_short)[:w]
        cw = cw.copy()
        cw[pos] ^= 1
        words.append(cw)
    words_arr = np.stack(words)
    synd_many = C3.syndromes_many(words_arr)
    assert synd_many.shape == (64, 26)
    many = C3.decode_many(words_arr, C3.t_full)
    for h in range(64):
        assert np.array_equal(synd_many[h], C3.syndromes(words_arr[h]))
        single = C3.decode(words_arr[h], C3.t_full)
        if single is None:
            assert many[h] is None
        else:
            assert many[h] is not None
            assert np.array_equal(many[h][0], single[0]) and many[h][1] == single[1]


def test_v3_dmin_soft_check():
    """No codeword of weight < 27 among 1e4 random nonzero messages
    (designed distance; soft statistical check, not a proof)."""
    gen = rng(SEED, b"v3-dmin")
    min_w = C3.n_short
    for _ in range(10_000):
        m = _rand_message_v3(gen)
        if not m.any():
            continue
        w = int(C3.encode(m).sum())
        min_w = min(min_w, w)
    print(f"  v3 min codeword weight over 1e4 random messages: {min_w}")
    assert min_w >= 27, min_w


def test_v2_v3_code_nesting():
    """MEASURED ALGEBRA, documented so nobody relies on code-level
    cross-format rejection: the v3 root set (alpha^1..26) CONTAINS the v2
    root set (alpha^1..20), so g_v2 | g_v3 and C_v3 is a SUBCODE of C_v2 —
    every v3 codeword decodes as a clean v2 codeword. Cross-format
    rejection is therefore ENTIRELY the labeled value-scramble's job
    (b"pilot-values-v2"/"-v3"; verified in tests/test_pilots_v3.py
    wrong-context gates). The other direction does reject: a v2 codeword
    generally has nonzero S_21..S_26 v3 syndromes."""
    g2 = sum(int(c) << i for i, c in enumerate(bch.generator_poly()))
    g3 = sum(int(c) << i for i, c in enumerate(C3.generator_poly()))
    assert _polymod2(g3, g2) == 0, "g_v2 must divide g_v3 (nested root sets)"
    gen = rng(SEED, b"cross")
    n_v3_rej = 0
    n_trials = 200
    for _ in range(n_trials):
        cw3 = C3.encode(_rand_message_v3(gen))
        res = bch.decode(cw3, bch.T_FULL)   # nesting: clean v2 acceptance
        assert res is not None and res[1] == 0
        cw2 = bch.encode(_rand_message(gen))
        if C3.decode(cw2, C3.t_full) is None:
            n_v3_rej += 1
    assert n_v3_rej >= 0.99 * n_trials, n_v3_rej


def test_code_for_version_dispatch():
    assert bch.code_for_version(2) is bch.CODE_V2
    assert bch.code_for_version(3) is bch.CODE_V3
    assert bch.CODE_V2.generator_poly().shape == (64,)
    try:
        bch.code_for_version(1)
        raise AssertionError("undefined layout_version must be rejected")
    except ValueError:
        pass
    # v2 module-level API delegates to CODE_V2 (frozen surface)
    gen = rng(SEED, b"dispatch")
    m = _rand_message(gen)
    assert np.array_equal(bch.encode(m), bch.CODE_V2.encode(m))


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")

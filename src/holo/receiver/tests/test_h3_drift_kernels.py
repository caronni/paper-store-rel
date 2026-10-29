from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from holo.receiver.lib import bch as h3_bch
from holo.receiver.lib import ldpc as h3_ldpc
from holo.receiver.tests import _h3_support

# The v1 receiver was retired 2026-09-05 (`src/holo/receive` deleted at
# 284ae3e), and with it this module's pava, owners and geometry legs: they
# compared holo3 against `holo.receive.{detect,_payload_context,
# _payload_sampling,color_calibration,payload_model}`, all of which are gone.
# Those seven test functions ran green one last time on the pre-deletion tree
# and are recorded there — PRESERVATION.md §2, "holo.receive legs".  The three
# kernel targets below survive: `holo.core` is format law and stays.  The
# geometry test was deleted outright rather than trimmed to its self-contained
# legs, because every one of them is already asserted in holo3's own unit
# lanes: the 131/17 lattice, its parity bit and the head/reveal masks in
# test_h3_lib_geometry.py, `rotated_points` there too (corner map and
# round-trip), and `head_sub_split` as the second bit of the site hash in
# test_h3_plugins_color.py.
v1_bch = pytest.importorskip("holo.core.bch")
v1_ldpc_construct = pytest.importorskip("holo.core.ldpc.construct")
v1_ldpc_decode = pytest.importorskip("holo.core.ldpc.decode")

pytestmark = pytest.mark.skipif(
    not _h3_support.slow_lane(),
    reason=f"cross-tree drift equivalence is a full-lane corpus: set "
           f"{_h3_support.SLOW_LANE_ENV}=1")

# frozen 2026-08-29 by the conversion's verify harness, deleted with the
# v1 receiver at 284ae3e
GPOLY_SHA = "a0be5064cfef57b2a84aaadbd7bd13b9772b1259fa041c25af0d7bde4922b684"
GPOLY_INT = 0x2C9352AA6CC054468311

# frozen 2026-08-29 from tests/holo/test_holo_ldpc.py through that same
# harness
GOLDEN_EDGES = {
    "r0547": "4cf6774a8fd3ed6d16878880f89778de"
             "172a6e3ed749e6f444537e726f4c9371",
    "r0550": "54c72b395776dd1aba2c65dfa49b1e3b"
             "9f7e4010266c477a6079b1d214ef477e",
    "r0625": "e98e65155f4e625f185fc202060d2bba"
             "4b6f23b70ad3786990ff77c0f059fb71",
    "r0700": "b1ef32ed91a17b6d74a20c3f0a415889"
             "aa1b0bae767b6c484bfee35b5c3e5913",
    "r0775": "8b0ec36d6bcad660056020e25bc196aa"
             "c749c7374ccbd576919369407eff0712",
    "r0850": "4be74ca98de10596d556d756914eaa45"
             "538fd22a78b5fee8d128dbcb22da33c7",
}

RATE_IDS = tuple(sorted(GOLDEN_EDGES))

# frozen 2026-09-04 from holo2.format.bch_batch at 4e6ec3e (the tree
# Phase 3 deleted 2026-09-05 at a805888), via measure/h3_freeze_holo2_pins.py,
# which went with the deletion.  holo2's batch
# BCH decoder is a SECOND, independently written implementation of the
# address code; these are its outputs over the seeded corpora below,
# keyed by corpus size so the pin also holds under the oracle sweeps.
# The oracle moved into this file — the law did not.
# (digest of the decoded rows, n_rows, n_decoded)
HOLO2_DECODE_MANY = {
    (400, 1600): ("e7619e4650950c5324bde0a4a192973e"
                  "828576e07e457086616a000acd1fce43", 2_000, 1_408),
    (60_000, 140_000): ("ce85ff0e0bce19c6dab46bc60fc4c5c5"
                        "b652dae4a5587be472b67fcbbdd6019a",
                        200_000, 122_479),
}
# (Berlekamp-Massey digest, Chien-mask digest, n_dirty, n_kept)
HOLO2_BATCH_INTERNALS = {
    2048: ("01165d144287deb0595f8f98c1ebaa7d"
           "36a3c732f573df9839f856fad9a162bd",
           "38205fe7245b53247e912f1a2b4199fd"
           "f1627317b5dd1b22998d0d8968d49ac3", 2_048, 2_025),
    8192: ("21f8cf38407cb73e36bde57e50802096"
           "b866f24fbd20d76543adcd11227d7781",
           "717dbddaaf381c06972b770cef39b32c"
           "404e155b67efddeab5388e5fb246e06e", 8_192, 8_126),
}

V1_LDPC_DATA = Path(v1_ldpc_construct.__file__).resolve().parent / "data"
H3_LDPC_DATA = Path(h3_ldpc.__file__).resolve().parent / "ldpc_data"

BCH_SEED = 20260828
LDPC_SEED = 20260828

# (n_random, n_near) and n_words for the two batch corpora, fast lane
# first: the frozen holo2 records below are keyed by them, so the pin
# holds under HOLO3_RUN_ORACLE_SWEEPS too
BCH_CORPUS_SIZES = ((400, 1600), (60_000, 140_000))
BCH_INTERNALS_SIZES = (2048, 8192)


def _n(fast: int, full: int) -> int:
    return full if _h3_support.oracle_sweeps() else fast


def bch_decode_corpus(n_random: int, n_near: int) -> np.ndarray:
    rng = np.random.default_rng(BCH_SEED + 4)
    batch = np.empty((n_random + n_near, h3_bch.N_WORD), dtype=np.uint8)
    batch[:n_random] = rng.integers(0, 2, size=(n_random, h3_bch.N_WORD))
    messages = rng.integers(0, 2, size=(n_near, h3_bch.K_MSG)).astype(np.uint8)
    errors = rng.integers(0, 16, size=n_near)
    for k in range(n_near):
        word = v1_bch.encode(messages[k])
        positions = rng.choice(h3_bch.N_WORD, size=int(errors[k]),
                               replace=False)
        word[positions] ^= 1
        batch[n_random + k] = word
    batch[n_random] = 0
    return batch[rng.permutation(batch.shape[0])]


def bch_dirty_syndromes(n_words: int) -> np.ndarray:
    rng = np.random.default_rng(BCH_SEED + 5)
    words = rng.integers(0, 2, size=(n_words, h3_bch.N_WORD)).astype(np.uint8)
    synd_rows = h3_bch._syndromes_many_words(words)
    return synd_rows[synd_rows.any(axis=1)]


def bch_kept_mask(terms: np.ndarray, length: np.ndarray) -> np.ndarray:
    return (length <= h3_bch.T) & (terms - 1 == length)


def array_digest(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        digest.update(str(array.dtype).encode())
        digest.update(str(array.shape).encode())
        digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def decode_rows_digest(rows: list) -> str:
    digest = hashlib.sha256()
    for row in rows:
        if row is None:
            digest.update(b"-")
            continue
        word, n_errors = row
        digest.update(b"+")
        digest.update(np.ascontiguousarray(word).tobytes())
        digest.update(int(n_errors).to_bytes(2, "big"))
    return digest.hexdigest()


def same_decode(a: object, b: object) -> bool:
    if a is None or b is None:
        return a is None and b is None
    word_a, n_a = a
    word_b, n_b = b
    return (int(n_a) == int(n_b) and word_a.dtype == np.uint8
            and np.array_equal(word_a, word_b))


def eq_arrays(a: np.ndarray, b: np.ndarray) -> bool:
    a = np.asarray(a)
    b = np.asarray(b)
    return (a.dtype == b.dtype and a.shape == b.shape
            and bool(np.array_equal(a, b)))


def test_bch_generator_polynomial_and_gf_tables_match_v1():
    poly = h3_bch.generator_poly()
    assert hashlib.sha256(poly.tobytes()).hexdigest() == GPOLY_SHA
    assert sum(int(c) << i for i, c in enumerate(poly)) == GPOLY_INT
    assert poly.dtype == np.uint8
    assert eq_arrays(poly, v1_bch.generator_poly())
    v1_exp, v1_log = v1_bch.gf_tables()
    assert eq_arrays(h3_bch._EXP, v1_exp)
    assert eq_arrays(h3_bch._LOG, v1_log)


def test_bch_shape_constants_match_v1():
    for name in ("N_FULL", "K_FULL", "T", "D_MIN", "SHORTEN_BY", "N_WORD",
                 "K_MSG", "N_PARITY", "GF_PRIM_POLY"):
        assert getattr(h3_bch, name) == getattr(v1_bch, name), name


def test_bch_encode_matches_v1_on_seeded_messages():
    rng = np.random.default_rng(BCH_SEED)
    for _ in range(_n(60, 500)):
        message = rng.integers(0, 2, size=h3_bch.K_MSG).astype(np.uint8)
        mine = h3_bch.encode(message)
        theirs = v1_bch.encode(message)
        assert mine.dtype == np.uint8
        assert eq_arrays(mine, theirs)


def test_bch_counter_round_trip_matches_v1_over_the_pad_layout():
    rng = np.random.default_rng(BCH_SEED + 1)
    counters = [0, 1, 2**18 - 1, *(int(v) for v in
                                   rng.integers(0, 1 << 18, size=_n(24, 400)))]
    for counter in counters:
        message = np.zeros(h3_bch.K_MSG, dtype=np.uint8)
        bits = [(counter >> (17 - i)) & 1 for i in range(18)]
        message[:18] = np.array(bits, dtype=np.uint8)
        word = h3_bch.encode(message)
        assert eq_arrays(word, v1_bch.encode(message))
        mine = h3_bch.decode(word)
        theirs = v1_bch.decode(word)
        assert same_decode(mine, theirs)
        assert eq_arrays(h3_bch.message_from_word(mine[0]), message)
        assert eq_arrays(v1_bch.message_from_word(theirs[0]), message)
        assert message[18:].sum() == 0


def test_bch_syndromes_match_v1_scalar_and_batch():
    rng = np.random.default_rng(BCH_SEED + 2)
    words = rng.integers(0, 2, size=(_n(200, 2000), h3_bch.N_WORD)).astype(
        np.uint8)
    for row in range(min(40, words.shape[0])):
        assert eq_arrays(h3_bch.syndromes(words[row]),
                         v1_bch.syndromes(words[row]))
    assert eq_arrays(h3_bch.syndromes_many(words),
                     v1_bch.syndromes_many(words))
    zero = np.zeros(h3_bch.N_WORD, dtype=np.uint8)
    assert eq_arrays(h3_bch.syndromes(zero), np.zeros(26, dtype=np.uint8))


@pytest.mark.parametrize("n_errors", list(range(0, h3_bch.T + 3)))
def test_bch_decode_ladder_agrees_with_v1_at_every_error_count(n_errors):
    rng = np.random.default_rng(BCH_SEED + 100 + n_errors)
    n_trials = _n(12, 120)
    refusals = 0
    for _ in range(n_trials):
        message = rng.integers(0, 2, size=h3_bch.K_MSG).astype(np.uint8)
        word = v1_bch.encode(message)
        corrupted = word.copy()
        positions = rng.choice(h3_bch.N_WORD, size=n_errors, replace=False)
        corrupted[positions] ^= 1
        mine = h3_bch.decode(corrupted)
        theirs = v1_bch.decode(corrupted)
        assert same_decode(mine, theirs), (n_errors, mine, theirs)
        if mine is None:
            refusals += 1
            continue
        if n_errors <= h3_bch.T:
            assert eq_arrays(mine[0], word)
            assert mine[1] == n_errors
    if n_errors <= h3_bch.T:
        assert refusals == 0
    else:
        assert refusals > 0, (
            f"e={n_errors} is beyond t=13 yet nothing refused — the "
            f"degraded ladder must bracket the cliff")


def test_bch_decode_erasures_matches_v1_including_the_budget_refusals():
    rng = np.random.default_rng(BCH_SEED + 3)
    accepted = 0
    refused = 0
    for _ in range(_n(200, 3000)):
        message = rng.integers(0, 2, size=h3_bch.K_MSG).astype(np.uint8)
        word = v1_bch.encode(message)
        n_erasures = int(rng.integers(0, 31))
        n_errors = int(rng.integers(0, 16))
        erasures = rng.choice(h3_bch.N_WORD, size=n_erasures, replace=False)
        clean = np.setdiff1d(np.arange(h3_bch.N_WORD), erasures)
        positions = rng.choice(clean, size=min(n_errors, clean.size),
                               replace=False)
        corrupted = word.copy()
        corrupted[positions] ^= 1
        corrupted[erasures] = rng.integers(0, 2, size=n_erasures).astype(
            np.uint8)
        mine = h3_bch.decode_erasures(corrupted, erasures)
        theirs = v1_bch.decode_erasures(corrupted, erasures)
        assert same_decode(mine, theirs)
        if mine is None:
            refused += 1
            continue
        accepted += 1
        if 2 * len(positions) + n_erasures <= 26:
            assert eq_arrays(mine[0], word)
    assert accepted > 0 and refused > 0


def test_bch_erasure_budget_boundary_agrees_on_both_sides():
    zero = np.zeros(h3_bch.N_WORD, dtype=np.uint8)
    era27 = np.arange(27, dtype=np.int64)
    assert h3_bch.decode_erasures(zero, era27) is None
    assert v1_bch.decode_erasures(zero, era27) is None
    word = v1_bch.encode(np.ones(h3_bch.K_MSG, dtype=np.uint8))
    trial = word.copy()
    trial[:26] ^= 1
    era26 = np.arange(26, dtype=np.int64)
    mine = h3_bch.decode_erasures(trial, era26)
    theirs = v1_bch.decode_erasures(trial, era26)
    assert same_decode(mine, theirs)
    assert mine is not None and mine[1] == 0
    assert eq_arrays(mine[0], word)


def test_bch_decode_many_is_bit_identical_to_v1_scalar_and_the_batch_record():
    sizes = BCH_CORPUS_SIZES[1 if _h3_support.oracle_sweeps() else 0]
    digest, n_rows, n_decoded_expected = HOLO2_DECODE_MANY[sizes]
    batch = bch_decode_corpus(*sizes)

    mine = h3_bch.decode_many(batch)
    v1_rows = v1_bch.decode_many(batch)
    assert len(mine) == len(v1_rows) == n_rows
    n_decoded = 0
    for i in range(len(mine)):
        assert same_decode(mine[i], v1_rows[i]), i
        n_decoded += mine[i] is not None
    assert n_decoded == n_decoded_expected
    assert 0 < n_decoded < len(mine)
    _h3_support.assert_golden("holo2 batch decode_many",
                              decode_rows_digest(mine), digest)
    assert h3_bch.decode_many(
        np.zeros((0, h3_bch.N_WORD), dtype=np.uint8)) == []


def test_bch_batch_internals_match_the_frozen_holo2_batch_record():
    n_words = BCH_INTERNALS_SIZES[1 if _h3_support.oracle_sweeps() else 0]
    bm_digest, chien_digest, n_dirty, n_kept = HOLO2_BATCH_INTERNALS[n_words]
    synd_rows = bch_dirty_syndromes(n_words)
    assert synd_rows.shape[0] == n_dirty
    sigma, terms, length = h3_bch.berlekamp_massey_many(synd_rows)
    _h3_support.assert_golden("holo2 berlekamp_massey_many",
                              array_digest(sigma, terms, length), bm_digest)
    kept = bch_kept_mask(terms, length)
    assert int(kept.sum()) == n_kept
    mask = h3_bch.chien_root_mask(sigma[kept, :h3_bch._SIGMA_WIDTH])
    _h3_support.assert_golden("holo2 chien_root_mask",
                              array_digest(mask), chien_digest)


def test_ldpc_catalogue_keys_match_the_frozen_rung_set():
    assert tuple(sorted(h3_ldpc.CODES)) == RATE_IDS


@pytest.mark.parametrize("rate_id", RATE_IDS)
def test_ldpc_edge_digest_and_derived_arrays_match_v1(rate_id):
    mine = h3_ldpc.CODES[rate_id]
    theirs = v1_ldpc_construct.load_code(rate_id)
    digest = hashlib.sha256(
        mine.edge_chk.astype("<i4").tobytes()
        + mine.edge_var.astype("<i4").tobytes()).hexdigest()
    _h3_support.assert_golden(f"ldpc edges {rate_id}", digest,
                              GOLDEN_EDGES[rate_id])
    assert mine.k_bits == theirs.spec.k_bits
    assert mine.n_bits == theirs.spec.n_bits
    for name in ("edge_chk", "edge_var", "chk_starts", "var_order",
                 "var_starts", "enc_info_col", "enc_rows", "enc_row_starts"):
        assert eq_arrays(getattr(mine, name), getattr(theirs, name)), name
    assert not mine.edge_chk.flags.writeable


@pytest.mark.parametrize("rate_id", RATE_IDS)
def test_ldpc_encode_matches_v1(rate_id):
    rng = np.random.default_rng(LDPC_SEED + RATE_IDS.index(rate_id))
    code = h3_ldpc.CODES[rate_id]
    for _ in range(_n(6, 60)):
        info = rng.integers(0, 2, code.k_bits, dtype=np.uint8)
        assert eq_arrays(h3_ldpc.encode(info, code),
                         v1_ldpc_decode.encode(info, rate_id))


def _ldpc_cases(rate_id: str, rng: np.random.Generator) -> list:
    code = h3_ldpc.CODES[rate_id]
    n, k = code.n_bits, code.k_bits
    cases: list[tuple[np.ndarray, int, float]] = []
    for _ in range(_n(2, 60)):
        info = rng.integers(0, 2, k, dtype=np.uint8)
        codeword = v1_ldpc_decode.encode(info, rate_id)
        cases.append(((2.0 * codeword - 1.0) * 8.0, 60, 0.8))
    for i in range(_n(2, 80)):
        info = rng.integers(0, 2, k, dtype=np.uint8)
        codeword = v1_ldpc_decode.encode(info, rate_id).astype(np.float64)
        p_flip = (0.02, 0.035, 0.05, 0.08)[i % 4]
        received = np.where(rng.random(n) < p_flip, 1.0 - codeword, codeword)
        magnitude = (4.0, 8.0, 2.5)[i % 3]
        max_iters = 150 if i % 10 == 7 else (0 if i % 10 == 8 else 60)
        alpha = 0.75 if i % 20 == 13 else 0.8
        cases.append(((2.0 * received - 1.0) * magnitude, max_iters, alpha))
    for i in range(_n(1, 40)):
        info = rng.integers(0, 2, k, dtype=np.uint8)
        codeword = v1_ldpc_decode.encode(info, rate_id).astype(np.float64)
        received = np.where(rng.random(n) < 0.02, 1.0 - codeword, codeword)
        llr = (2.0 * received - 1.0) * 6.0
        llr[rng.random(n) < 0.1 + 0.3 * rng.random()] = 0.0
        cases.append((llr, 150 if i % 8 == 5 else 60, 0.8))
    for i in range(_n(1, 10)):
        info = rng.integers(0, 2, k, dtype=np.uint8)
        codeword = v1_ldpc_decode.encode(info, rate_id).astype(np.float64)
        received = np.where(rng.random(n) < 0.05, 1.0 - codeword, codeword)
        llr = (2.0 * received - 1.0) * 4.0
        known = rng.choice(n, size=200, replace=False)
        llr[known] = np.where(codeword[known] > 0.5, np.inf, -np.inf)
        if i % 2:
            wrong = rng.choice(known, size=3, replace=False)
            llr[wrong] = -llr[wrong]
        cases.append((llr, 60, 0.8))
    for i in range(_n(1, 10)):
        cases.append((rng.normal(0.0, 3.0, n), 150 if i % 2 else 60, 0.8))
    return cases


@pytest.mark.parametrize("rate_id", RATE_IDS)
def test_ldpc_decode_is_bit_identical_to_v1_including_failures(rate_id):
    rng = np.random.default_rng(LDPC_SEED + 1000 + RATE_IDS.index(rate_id))
    code = h3_ldpc.CODES[rate_id]
    outcomes = {True: 0, False: 0}
    for llr, max_iters, alpha in _ldpc_cases(rate_id, rng):
        ok3, hard3, iters3, ext3 = h3_ldpc.decode(llr, code, max_iters, alpha)
        ok1, hard1, iters1, ext1 = v1_ldpc_decode.decode_soft(
            llr, rate_id, max_iters, alpha)
        assert ok3 == ok1
        assert eq_arrays(hard3, hard1)
        assert iters3 == iters1
        assert ext3.dtype == ext1.dtype == np.float64
        assert np.array_equal(ext3, ext1)
        outcomes[bool(ok3)] += 1
    assert outcomes[True] > 0 and outcomes[False] > 0


def test_ldpc_shape_constants_match_the_mother_code_geometry():
    assert h3_ldpc.N_BITS == 4096
    assert h3_ldpc.Z == 64
    assert h3_ldpc.LLR_CLIP == 20.0
    assert h3_ldpc.LLR_KNOWN == 1e9
    for rate_id in RATE_IDS:
        assert h3_ldpc.CODES[rate_id].n_bits == h3_ldpc.N_BITS

from __future__ import annotations

import hashlib
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo3.lib import bch as h3_bch
from holo3.lib import decimate as h3_dec
from holo3.lib import geometry as h3_geom
from holo3.lib import ldpc as h3_ldpc
from holo3.lib import owners as h3_owners
from holo3.lib import pava as h3_pava
from holo3.tests import _h3_support

v1_bch = pytest.importorskip("holo.core.bch")
h2_bch_batch = pytest.importorskip("holo2.format.bch_batch")
v1_ldpc_construct = pytest.importorskip("holo.core.ldpc.construct")
v1_ldpc_decode = pytest.importorskip("holo.core.ldpc.decode")
v1_detect = pytest.importorskip("holo.receive.detect")
v1_ctx = pytest.importorskip("holo.receive._payload_context")
v1_sampling = pytest.importorskip("holo.receive._payload_sampling")
v1_colcal = pytest.importorskip("holo.receive.color_calibration")
v1_payload_model = pytest.importorskip("holo.receive.payload_model")
h2_geometry = pytest.importorskip("holo2.solve.geometry")
h2_place_shared = pytest.importorskip("holo2.solve.place_shared")
h2_scale_space = pytest.importorskip("holo2.capture.scale_space")
h2_scan = pytest.importorskip("holo2.capture.scan")

pytestmark = pytest.mark.skipif(
    not _h3_support.slow_lane(),
    reason=f"cross-tree drift equivalence is a full-lane corpus: set "
           f"{_h3_support.SLOW_LANE_ENV}=1")

# frozen 2026-08-29 from _distill/verify/verify_bch.py:15-16
GPOLY_SHA = "a0be5064cfef57b2a84aaadbd7bd13b9772b1259fa041c25af0d7bde4922b684"
GPOLY_INT = 0x2C9352AA6CC054468311

# frozen 2026-08-29 from tests/holo/test_holo_ldpc.py via verify_ldpc.py:33-46
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

V1_LDPC_DATA = Path(v1_ldpc_construct.__file__).resolve().parent / "data"
H3_LDPC_DATA = Path(h3_ldpc.__file__).resolve().parent / "ldpc_data"

BCH_SEED = 20260828
LDPC_SEED = 20260828
LIB_SEED = 20260828


def _n(fast: int, full: int) -> int:
    return full if _h3_support.oracle_sweeps() else fast


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


def test_bch_decode_many_is_bit_identical_to_v1_scalar_and_holo2_batch():
    rng = np.random.default_rng(BCH_SEED + 4)
    n_random = _n(400, 60_000)
    n_near = _n(1600, 140_000)
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
    batch = batch[rng.permutation(batch.shape[0])]

    mine = h3_bch.decode_many(batch)
    v1_rows = v1_bch.decode_many(batch)
    h2_rows = h2_bch_batch.decode_many(batch)
    assert len(mine) == len(v1_rows) == len(h2_rows)
    n_decoded = 0
    for i in range(len(mine)):
        assert same_decode(mine[i], v1_rows[i]), i
        assert same_decode(mine[i], h2_rows[i]), i
        n_decoded += mine[i] is not None
    assert 0 < n_decoded < len(mine)
    assert h3_bch.decode_many(
        np.zeros((0, h3_bch.N_WORD), dtype=np.uint8)) == []


def test_bch_batch_internals_lockstep_with_holo2_on_dirty_syndromes():
    rng = np.random.default_rng(BCH_SEED + 5)
    words = rng.integers(0, 2, size=(_n(2048, 8192), h3_bch.N_WORD)).astype(
        np.uint8)
    synd_rows = h3_bch._syndromes_many_words(words)
    dirty = synd_rows.any(axis=1)
    assert dirty.any()
    sigma3, terms3, length3 = h3_bch.berlekamp_massey_many(synd_rows[dirty])
    sigma2, terms2, length2 = h2_bch_batch.berlekamp_massey_many(
        synd_rows[dirty])
    assert eq_arrays(sigma3, sigma2)
    assert eq_arrays(terms3, terms2)
    assert eq_arrays(length3, length2)
    kept = (length3 <= h3_bch.T) & (terms3 - 1 == length3)
    assert kept.any()
    mask3 = h3_bch.chien_root_mask(sigma3[kept, :h3_bch._SIGMA_WIDTH])
    mask2 = h2_bch_batch.chien_root_mask(sigma2[kept, :h3_bch._SIGMA_WIDTH])
    assert eq_arrays(mask3, mask2)


@pytest.mark.parametrize("rate_id", RATE_IDS)
def test_ldpc_mother_code_json_is_byte_identical_to_v1(rate_id):
    mine = (H3_LDPC_DATA / f"{rate_id}.json").read_bytes()
    theirs = (V1_LDPC_DATA / f"{rate_id}.json").read_bytes()
    assert mine == theirs, (
        f"{rate_id}.json differs from src/holo's copy — the frozen mother "
        f"codes ARE the format, so this is a printed-format fork")


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


def test_pava_nodes_and_calibration_match_v1_detect():
    rng = np.random.default_rng(LIB_SEED)
    compared = 0
    for trial in range(_n(10, 30)):
        n = int(rng.integers(20, 400))
        scores = rng.normal(size=n).astype(np.float32).astype(np.float64)
        if trial % 3 == 0:
            scores = np.round(scores, 1)
        labels = rng.integers(0, 2, size=n).astype(bool)
        if labels.sum() < 2 or (~labels).sum() < 2:
            continue
        knots3, probs3 = h3_pava._pava_nodes(scores, labels)
        knots1, probs1 = v1_detect._pava_nodes(scores, labels)
        assert eq_arrays(knots3, knots1)
        assert eq_arrays(probs3, probs1)
        compared += 1
    assert compared > 0

    n = 200
    scores = rng.normal(size=n)
    labels = (scores + rng.normal(scale=0.5, size=n)) > 0
    knots, probs = v1_detect._pava_nodes(scores, labels)
    calibration = v1_detect.Calibration("w1", knots, probs, n)
    query = rng.normal(size=500) * 2.0
    assert eq_arrays(
        h3_pava.calibration_probability(query, calibration.knots,
                                        calibration.probabilities),
        calibration.probability(query))
    assert eq_arrays(
        h3_pava.calibration_llr(query, calibration.knots,
                                calibration.probabilities),
        calibration.llr(query))
    for k in (1, 2, 10, 100, 4096):
        assert h3_pava.clamp_for(k) == v1_detect.clamp_for(k)


def test_pava_offset_solver_and_losses_match_v1():
    rng = np.random.default_rng(LIB_SEED + 1)
    for _ in range(_n(20, 60)):
        m = int(rng.integers(3, 200))
        llr = rng.normal(scale=3.0, size=m)
        labels = rng.integers(0, 2, size=m).astype(bool)
        weights = rng.uniform(0.1, 1.0, size=m)
        assert (h3_pava._solve_offset(llr, labels, weights)
                == v1_detect._solve_offset(llr, labels, weights))
    for all_true in (False, True):
        llr = rng.normal(size=40)
        labels = np.full(40, all_true)
        weights = np.ones(40)
        assert (h3_pava._solve_offset(llr, labels, weights)
                == v1_detect._solve_offset(llr, labels, weights))

    m = 300
    llr = rng.normal(scale=4.0, size=m)
    labels = rng.integers(0, 2, size=m).astype(bool)
    weights = rng.uniform(0.1, 2.0, size=m)
    assert (h3_pava._logloss(llr, labels, weights)
            == v1_detect._logloss(llr, labels, weights))
    assert (h3_pava._binary_logloss(llr, labels)
            == v1_ctx._binary_logloss(llr, labels))
    assert (h3_pava._binary_logloss(llr, labels, weights)
            == v1_ctx._binary_logloss(llr, labels, weights))
    probabilities = np.clip(rng.uniform(size=m), 1e-4, 1.0 - 1e-4)
    y = labels.astype(np.float64)
    expected = float(-np.mean(y * np.log(probabilities)
                              + (1.0 - y) * np.log(1.0 - probabilities)))
    assert h3_pava.probability_logloss(probabilities, labels) == expected


def test_pava_ordered_context_offsets_match_v1_detect():
    rng = np.random.default_rng(LIB_SEED + 2)
    for _ in range(_n(6, 20)):
        m = int(rng.integers(200, 800))
        llr = rng.normal(scale=2.0, size=m)
        bins = rng.integers(0, 9, size=m).astype(np.int64)
        n_sites = max(10, m // 2)
        site_ids = rng.integers(0, n_sites, size=m).astype(np.int64)
        site_labels = rng.integers(0, 2, size=n_sites).astype(bool)
        observations = v1_detect.ContextObservations(
            "r1", llr, bins, site_labels[site_ids], site_ids)
        mine = h3_pava._ordered_context_offsets(
            observations.baseline_llr, observations.neighbour_count,
            observations.labels, observations.weights)
        assert eq_arrays(mine, v1_detect._ordered_context_offsets(observations))


def test_pava_class_balanced_weights_match_v1_color_calibration():
    rng = np.random.default_rng(LIB_SEED + 3)
    for _ in range(_n(8, 20)):
        m = int(rng.integers(5, 300))
        states = rng.integers(0, 7, size=m)
        assert eq_arrays(h3_pava.class_balanced_weights(states),
                         v1_colcal.class_balanced_weights(states))
    empty = np.zeros(0, np.int64)
    assert eq_arrays(h3_pava.class_balanced_weights(empty),
                     v1_colcal.class_balanced_weights(empty))


def test_geometry_affine_family_matches_holo2():
    rng = np.random.default_rng(LIB_SEED + 4)
    compared = 0
    for _ in range(_n(15, 40)):
        terms = tuple(float(v) for v in rng.normal(scale=5.0, size=6))
        if abs(terms[0] * terms[4] - terms[1] * terms[3]) < 1e-6:
            continue
        assert (h3_geom.affine_terms(h3_geom.affine_matrix(terms))
                == h2_geometry.affine_terms(h2_geometry.affine_matrix(terms)))
        assert (h3_geom.invert_affine(terms)
                == h2_geometry.invert_affine(terms))
        ys = rng.normal(scale=100.0, size=50)
        xs = rng.normal(scale=100.0, size=50)
        mine_y, mine_x = h3_geom.apply_affine(terms, ys, xs)
        theirs_y, theirs_x = h2_geometry.apply_affine(terms, ys, xs)
        assert eq_arrays(mine_y, theirs_y)
        assert eq_arrays(mine_x, theirs_x)
        dy, dx = float(rng.normal()), float(rng.normal())
        assert (h3_geom.shift_affine(terms, dy, dx)
                == h2_geometry.shift_affine(terms, dy, dx))
        compared += 1
    assert compared > 0


def test_geometry_rescale_and_compose_match_holo2_place_shared():
    rng = np.random.default_rng(LIB_SEED + 5)
    scales = (Fraction(2), Fraction(3), Fraction(4), Fraction(16),
              Fraction(8, 3), Fraction(12, 5), Fraction(1))
    for _ in range(_n(6, 20)):
        terms = tuple(float(v) for v in rng.normal(scale=7.0, size=6))
        for scale in scales:
            assert (h3_geom.rescale_pixels(terms, scale)
                    == h2_place_shared._rescale_pixels(terms, scale))
            identity = tuple(float(t) for t in terms)
            expect_to = (identity if scale == 1
                         else h2_place_shared._rescale_pixels(terms, scale))
            expect_from = (identity if scale == 1
                           else h2_place_shared._rescale_pixels(terms,
                                                                1 / scale))
            assert h3_geom.compose_to_native(terms, scale) == expect_to
            assert h3_geom.compose_from_native(terms, scale) == expect_from


def test_geometry_window_layout_constants_and_starts_match_holo2():
    assert ((h3_geom.WINDOW_CELLS, h3_geom.WINDOW_STEP_CELLS,
             h3_geom.LAYOUT_MIN_WINDOW_CELLS, h3_geom.TILE_CELLS)
            == (h2_geometry.WINDOW_CELLS, h2_geometry.WINDOW_STEP_CELLS,
                h2_geometry.LAYOUT_MIN_WINDOW_CELLS, h2_geometry.TILE_CELLS))
    for n in range(1, _n(201, 601)):
        assert h3_geom.window_starts(n) == h2_geometry.window_starts(n)


def test_geometry_site_hash_parity_and_rotation_match_the_v1_consumers():
    rng = np.random.default_rng(LIB_SEED + 6)
    cells = rng.integers(0, 5000, size=(4000, 2)).astype(np.int64)
    y, x = cells[:, 0], cells[:, 1]
    assert eq_arrays(h3_geom.site_parity(y, x), (131 * y + 17 * x) & 1)
    keys = np.column_stack((np.zeros(y.size, np.int64), y, x))
    assert eq_arrays((h3_geom.site_hash(y, x) & 2) == 0,
                     v1_colcal.head_sub_split(keys))
    assert eq_arrays(h3_geom.site_hash(y, x) & 12, (131 * y + 17 * x) & 12)
    for rot_k in range(4):
        points = rng.integers(0, 300, size=(500, 2)).astype(np.int64)
        shape = (int(rng.integers(300, 400)), int(rng.integers(300, 400)))
        assert eq_arrays(h3_geom.rotated_points(points, shape, rot_k),
                         v1_sampling.rotated_points(points, shape, rot_k))
    ty3, tx3 = h3_geom.tile_of_cell(y, x)
    ty2, tx2 = h2_geometry.tile_of_cell(y, x)
    assert eq_arrays(ty3, ty2)
    assert eq_arrays(tx3, tx2)


def test_decimate_ppc_ladder_matches_holo2_scale_space():
    pairs = [
        (2400, Fraction(2, 600)), (4800, Fraction(2, 600)),
        (1200, Fraction(3, 600)), (2400, Fraction(3, 600)),
        (1200, Fraction(2, 600)), (4800, Fraction(3, 600)),
        (1200.0, Fraction(3, 600)), ("2400", Fraction(2, 600)),
        (1600, Fraction(2, 600)), (600, Fraction(3, 600)),
    ]
    for dpi, pitch in pairs:
        assert (h3_dec.auto_ppc_levels(dpi, pitch)
                == h2_scale_space.auto_ppc_levels(dpi, pitch)), (dpi, pitch)
        assert (h3_dec.native_pixels_per_cell(dpi, pitch)
                == h2_scale_space.native_pixels_per_cell(dpi, pitch))
    assert h3_dec.as_fraction(1200.0) == Fraction(1200)
    assert h3_dec.as_fraction(0.1) == Fraction(1, 10)


def test_decimate_area_pixel_transform_matches_holo2():
    rng = np.random.default_rng(LIB_SEED + 7)
    for scale in (Fraction(2), Fraction(3), Fraction(16), Fraction(8, 3),
                  Fraction(1)):
        mine = h3_dec.AreaPixelTransform(scale)
        theirs = h2_scale_space.AreaPixelTransform(scale)
        for length in (0, 1, 7, 100, 4801):
            assert mine.output_length(length) == theirs.output_length(length)
        points = rng.normal(scale=1000.0, size=(200, 2))
        assert eq_arrays(mine.source_to_view_points(points),
                         theirs.source_to_view_points(points))
        assert eq_arrays(mine.view_to_source_points(points),
                         theirs.view_to_source_points(points))
        affine = rng.normal(scale=8.0, size=(2, 3))
        assert eq_arrays(mine.source_to_view_affine(affine),
                         theirs.source_to_view_affine(affine))
        assert eq_arrays(mine.view_to_source_affine(affine),
                         theirs.view_to_source_affine(affine))


@pytest.mark.parametrize("factor", (2, 3, 4, 6, 8, 16))
def test_decimate_box_kernels_match_holo2_and_are_chunk_invariant(factor):
    rng = np.random.default_rng(LIB_SEED + 8 + factor)
    h = int(rng.integers(3 * factor + 1, 6 * factor + 5))
    w = int(rng.integers(3 * factor + 1, 6 * factor + 5))
    grey = rng.integers(0, 256, size=(h, w)).astype(np.uint8)
    rgb = rng.integers(0, 256, size=(h, w, 3)).astype(np.uint8)
    mine = h3_dec.AreaPixelTransform(Fraction(factor))
    theirs = h2_scale_space.AreaPixelTransform(Fraction(factor))
    assert eq_arrays(h3_dec.area_decimate(grey, mine),
                     h2_scale_space.area_decimate(grey, theirs))
    assert eq_arrays(h3_dec.area_decimate(rgb, mine),
                     h2_scale_space.area_decimate(rgb, theirs))
    assert eq_arrays(h3_dec.area_decimate_rgb(rgb, mine),
                     h2_scale_space.area_decimate_rgb(rgb, theirs))
    assert eq_arrays(h3_dec.area_decimate(grey, mine, chunk_rows=1),
                     h3_dec.area_decimate(grey, mine))


@pytest.mark.parametrize("scale", (Fraction(3, 2), Fraction(8, 3),
                                   Fraction(5, 3), Fraction(12, 5)))
def test_decimate_rational_kernels_match_holo2_bit_exactly(scale):
    rng = np.random.default_rng(
        LIB_SEED + 40 + 7 * scale.numerator + scale.denominator)
    grey = rng.integers(0, 256, size=(41, 33)).astype(np.uint8)
    mine = h3_dec.AreaPixelTransform(scale)
    theirs = h2_scale_space.AreaPixelTransform(scale)
    assert eq_arrays(h3_dec.area_decimate(grey, mine),
                     h2_scale_space.area_decimate(grey, theirs))
    assert eq_arrays(h3_dec.area_decimate(grey, mine, chunk_rows=1),
                     h3_dec.area_decimate(grey, mine))


def test_decimate_luma_matches_holo2_scan():
    rng = np.random.default_rng(LIB_SEED + 9)
    rgb = rng.integers(0, 256, size=(64, 48, 3)).astype(np.uint8)
    grey = rng.integers(0, 256, size=(64, 48)).astype(np.uint8)
    assert eq_arrays(h3_dec.luma_f32(grey), h2_scan._raw_luma(grey))
    assert eq_arrays(h3_dec.luma_f32(rgb), h2_scan._raw_luma(rgb))
    assert eq_arrays(
        h3_dec.plane_mean_luma_f32(rgb[..., 0], rgb[..., 1], rgb[..., 2]),
        rgb.mean(axis=2, dtype=np.float32))


def _synth_owner_candidates(seed: int, n_windows: int, pages: int,
                            shape_yx: tuple[int, int]) -> list:
    rng = np.random.default_rng(seed)
    candidates = []
    for window_index in range(n_windows):
        page = int(rng.integers(0, pages))
        n = int(rng.integers(0, 200))
        cells = np.column_stack((
            rng.integers(0, shape_yx[0], size=n),
            rng.integers(0, shape_yx[1], size=n))).astype(np.int64)
        cells = np.unique(cells, axis=0)
        rows = np.arange(cells.shape[0], dtype=np.int32)
        values = rng.normal(size=(cells.shape[0], 1)).astype(np.float32)
        candidates.append((window_index, page, cells, rows, values))
    return candidates


def _owners_equal(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    for row_a, row_b in zip(a, b):
        if row_a[0] != row_b[0]:
            return False
        for value_a, value_b in zip(row_a[1:], row_b[1:]):
            if not eq_arrays(value_a, value_b):
                return False
    return True


def test_owners_freeze_page_owners_matches_v1_payload_model():
    shape = (192, 256)
    for trial in range(_n(4, 10)):
        candidates = _synth_owner_candidates(1000 + trial, 12, 3, shape)
        assert _owners_equal(h3_owners.freeze_page_owners(candidates, shape),
                             v1_payload_model.freeze_page_owners(candidates,
                                                                 shape))


def test_owners_order_keys_reproduce_v1_on_the_key_sorted_list():
    shape = (192, 256)
    candidates = _synth_owner_candidates(77, 12, 3, shape)
    keys = [(float(i % 5) * 0.25, (i % 3, i % 4, 7, 9), "g")
            for i in range(len(candidates))]
    permutation = list(np.random.default_rng(5).permutation(len(candidates)))
    shuffled = [candidates[i] for i in permutation]
    shuffled_keys = [keys[i] for i in permutation]
    key_sorted = [candidate for _key, candidate in
                  sorted(zip(shuffled_keys, shuffled), key=lambda p: p[0])]
    assert _owners_equal(
        h3_owners.freeze_page_owners(shuffled, shape, shuffled_keys),
        v1_payload_model.freeze_page_owners(key_sorted, shape))

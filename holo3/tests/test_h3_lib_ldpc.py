from __future__ import annotations

import dataclasses
import hashlib

import numpy as np
import pytest

from holo3.lib import ldpc
from holo3.tests import _h3_support

N_BITS = 4096
Z = 64
LLR_CLIP = 20.0
LLR_KNOWN = 1e9

RATE_IDS = ("r0547", "r0550", "r0625", "r0700", "r0775", "r0850")
K_BITS = {"r0547": 2240, "r0550": 2240, "r0625": 2560,
          "r0700": 2880, "r0775": 3200, "r0850": 3520}
EDGE_COUNTS = {"r0547": 14911, "r0550": 14911, "r0625": 16127,
               "r0700": 17343, "r0775": 16191, "r0850": 14783}

# frozen 2026-08-29, hand-copied from tests/holo/test_holo_ldpc.py
# GOLDEN_EDGES: sha256 over the '<i4' lexsorted edge_chk bytes then edge_var
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

# the frozen mother codes ARE the format: file digests, not derived arrays
DATA_SHA256 = {
    "r0547": "d1439d31b539786ace5e1bab28f6325f"
             "9e1608993652ad81d4a8048ef22df352",
    "r0550": "aaa7bce509b23c52f201af329d4a9399"
             "911c6c20f4fa3ca5382f883e4dc1d65d",
    "r0625": "b05aa66f85d40f0a9c38506cc840bc25"
             "b15ffacca6dc29c77d89d15083a51ce1",
    "r0700": "e5a774afa959e20ae8d4d2dccdef8594"
             "b2801fe281691dade6b4247451499d54",
    "r0775": "a1260e98afb6ca4b35b7157d61077fbf"
             "b2cf79f3e1dec3fc51f58669f49ec6d6",
    "r0850": "3f9fa52042a2bef3c6f42bbd9954aeca"
             "72dd174d05ca3cbed04b1526b4318d63",
}

# measured under env314t 2026-08-29 (numpy of this interpreter, NOT ported
# from v1's suite): rate, case, max_iters, alpha, syndrome_ok, n_iters,
# sha256[:32] of hard bits, sha256[:32] of extrinsic, wrong info bits
DECODE_VECTORS = (
    ("r0550", "clean", 60, 0.8, True, 0,
     "fb148b46d70ac81e25cca5e6900ec2cf",
     "c35020473aed1b4642cd726cad727b63", 0),
    ("r0550", "bsc02", 60, 0.8, True, 4,
     "419d32a4f397db44d83e3f1838ba8d2a",
     "bb334e6f825b7fb2844ca716405fb3e6", 0),
    ("r0550", "bsc05", 60, 0.8, True, 10,
     "ec8dbda5c9e8f82679a70d654f2673a7",
     "142b4f1e1bbf86d6411f2d6c153e094d", 0),
    ("r0550", "erasure", 150, 0.8, True, 16,
     "0db908926a558cac3feb5917035a0b56",
     "3d9bbda83d28acd91d705c9a3e6ef1ce", 0),
    ("r0550", "junk", 60, 0.8, False, 120,
     "b21e8a573aaae465b026317820623925",
     "92c89f2f955cb526033837b6e0ca2976", 1113),
    ("r0547", "bsc035", 60, 0.8, True, 10,
     "2e78e72850128f53dc5d0fabfa760ec4",
     "cdc387eca5d27eb6a52d1f3e31e0e304", 0),
    ("r0625", "bsc035", 60, 0.8, True, 14,
     "153c99d3588bb3ba57bdc2a4d5ed70e4",
     "cf6d7ba8ec372bb192dd4bbe9908c4e1", 0),
    ("r0700", "bsc02", 60, 0.75, True, 8,
     "fbb702be7dda794c92e8a312ca577e6d",
     "d945b1f91760c22be8f29226985c1ea6", 0),
    ("r0775", "bsc05", 150, 0.8, False, 300,
     "0f0014ecf9eeb27f8895febb506e45d9",
     "e9b07a5f2631219ceae55f99eaf2b4ce", 199),
    ("r0850", "clean", 0, 0.8, True, 0,
     "ac4b12679eadc87075a74c82cfb679d7",
     "c35020473aed1b4642cd726cad727b63", 0),
    ("r0850", "bsc08", 60, 0.8, False, 120,
     "c98e1914e7bf2c677ef8f28da6bf300c",
     "c1cf855cee6847e6cbe21513840d1a0c", 256),
    ("r0700", "known_inf", 60, 0.8, False, 120,
     "d94a7257ded1d50a46701d1ac47c6616",
     "50aa0da34474aea0c7c523d5478324f2", 127),
)

BSC_RATES = {"bsc02": 0.02, "bsc035": 0.035, "bsc05": 0.05, "bsc08": 0.08}


def _digest(array: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(array).tobytes()).hexdigest()[:32]


def _vector_llr(rate_id: str, case: str, seed: int
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    code = ldpc.CODES[rate_id]
    rng = np.random.default_rng(seed)
    info = rng.integers(0, 2, code.k_bits, dtype=np.uint8)
    codeword = ldpc.encode(info, code).astype(np.float64)
    if case == "clean":
        return info, codeword, (2.0 * codeword - 1.0) * 8.0
    if case == "junk":
        return info, codeword, rng.normal(0.0, 3.0, code.n_bits)
    if case == "erasure":
        received = np.where(rng.random(code.n_bits) < 0.02,
                            1.0 - codeword, codeword)
        llr = (2.0 * received - 1.0) * 6.0
        llr[rng.random(code.n_bits) < 0.25] = 0.0
        return info, codeword, llr
    if case == "known_inf":
        received = np.where(rng.random(code.n_bits) < 0.05,
                            1.0 - codeword, codeword)
        llr = (2.0 * received - 1.0) * 4.0
        known = rng.choice(code.n_bits, size=200, replace=False)
        llr[known] = np.where(codeword[known] > 0.5, np.inf, -np.inf)
        return info, codeword, llr
    received = np.where(rng.random(code.n_bits) < BSC_RATES[case],
                        1.0 - codeword, codeword)
    return info, codeword, (2.0 * received - 1.0) * 6.0


def test_ldpc_constants_are_the_frozen_format_law():
    assert (ldpc.N_BITS, ldpc.Z) == (N_BITS, Z)
    assert (ldpc.LLR_CLIP, ldpc.LLR_KNOWN) == (LLR_CLIP, LLR_KNOWN)
    assert tuple(sorted(ldpc.CODES)) == tuple(sorted(RATE_IDS))
    assert ldpc._RATE_IDS == RATE_IDS


@pytest.mark.parametrize("rate_id", RATE_IDS)
def test_rung_geometry_is_pinned_here_because_the_loader_never_checks_it(
        rate_id):
    code = ldpc.CODES[rate_id]
    assert code.rate_id == rate_id
    assert code.n_bits == N_BITS
    assert code.k_bits == K_BITS[rate_id]
    assert code.k_bits % Z == 0
    assert code.edge_chk.size == EDGE_COUNTS[rate_id]
    assert code.edge_var.size == code.edge_chk.size
    assert code.chk_starts.size == code.n_bits - code.k_bits
    assert code.var_starts.size == code.n_bits
    assert code.var_order.size == code.edge_chk.size
    assert (code.edge_chk.dtype, code.edge_var.dtype) == (
        np.int32, np.int32)
    assert bool((np.diff(code.edge_chk) >= 0).all())
    assert int(np.bincount(code.edge_chk).min()) >= 2
    assert int(np.bincount(code.edge_var, minlength=code.n_bits).min()) >= 1


@pytest.mark.parametrize("rate_id", RATE_IDS)
def test_edge_digests_reproduce_the_frozen_mother_code(rate_id):
    code = ldpc.CODES[rate_id]
    digest = hashlib.sha256(
        code.edge_chk.astype("<i4").tobytes()
        + code.edge_var.astype("<i4").tobytes()).hexdigest()
    _h3_support.assert_golden(f"{rate_id} edge digest", digest,
                              GOLDEN_EDGES[rate_id])


@pytest.mark.parametrize("rate_id", RATE_IDS)
def test_mother_code_json_files_are_frozen_bytes(rate_id):
    path = ldpc._DATA_DIR / f"{rate_id}.json"
    _h3_support.assert_golden(
        f"{rate_id}.json sha256",
        hashlib.sha256(path.read_bytes()).hexdigest(), DATA_SHA256[rate_id])


@pytest.mark.parametrize("rate_id", RATE_IDS)
def test_loaded_code_arrays_are_read_only_and_the_record_is_frozen(rate_id):
    code = ldpc.CODES[rate_id]
    for name in ("edge_chk", "edge_var", "chk_starts", "var_order",
                 "var_starts", "enc_info_col", "enc_rows", "enc_row_starts"):
        assert not getattr(code, name).flags.writeable, name
    with pytest.raises(ValueError):
        code.edge_chk[0] = 0
    with pytest.raises(dataclasses.FrozenInstanceError):
        code.rate_id = "r9999"


@pytest.mark.parametrize("rate_id", RATE_IDS)
def test_encode_is_systematic_and_lands_on_a_zero_syndrome_codeword(rate_id):
    code = ldpc.CODES[rate_id]
    rng = np.random.default_rng(20260829)
    info = rng.integers(0, 2, code.k_bits, dtype=np.uint8)
    codeword = ldpc.encode(info, code)
    assert codeword.shape == (N_BITS,) and codeword.dtype == np.uint8
    assert np.array_equal(codeword[:code.k_bits], info)
    syndrome = np.bitwise_xor.reduceat(codeword[code.edge_var],
                                       code.chk_starts)
    assert not syndrome.any()
    accepted, hard, n_iters, extrinsic = ldpc.decode(
        (2.0 * codeword - 1.0) * 8.0, code, 60, 0.8)
    assert accepted and n_iters == 0
    assert np.array_equal(hard, codeword)
    assert extrinsic.dtype == np.float64 and not extrinsic.any()


@pytest.mark.parametrize(
    "rate_id, case, max_iters, alpha, accepted, n_iters, hard_sha, "
    "extrinsic_sha, n_wrong", DECODE_VECTORS)
def test_frozen_decode_vectors_measured_under_this_interpreter(
        rate_id, case, max_iters, alpha, accepted, n_iters, hard_sha,
        extrinsic_sha, n_wrong):
    index = [row[:2] for row in DECODE_VECTORS].index((rate_id, case))
    info, _codeword, llr = _vector_llr(rate_id, case, 20260829 + index)
    got_ok, hard, got_iters, extrinsic = ldpc.decode(
        llr, ldpc.CODES[rate_id], max_iters, alpha)
    assert (bool(got_ok), int(got_iters)) == (accepted, n_iters)
    _h3_support.assert_golden(f"{rate_id}/{case} hard bits",
                              _digest(hard), hard_sha)
    _h3_support.assert_golden(f"{rate_id}/{case} extrinsic",
                              _digest(extrinsic), extrinsic_sha)
    assert int(np.count_nonzero(hard[:info.size] != info)) == n_wrong
    assert hard.dtype == np.uint8 and extrinsic.dtype == np.float64


def test_a_positive_llr_reads_as_a_zero_bit():
    code = ldpc.CODES["r0550"]
    rng = np.random.default_rng(20260829)
    codeword = ldpc.encode(
        rng.integers(0, 2, code.k_bits, dtype=np.uint8), code)
    flipped = ldpc.decode((1.0 - 2.0 * codeword) * 8.0, code, 0, 0.8)
    assert np.array_equal(flipped[1], 1 - codeword)


def test_finite_llrs_beyond_the_clip_decode_identically_to_the_clip():
    code = ldpc.CODES["r0550"]
    rng = np.random.default_rng(20260829)
    codeword = ldpc.encode(
        rng.integers(0, 2, code.k_bits, dtype=np.uint8), code).astype(
            np.float64)
    received = np.where(rng.random(code.n_bits) < 0.05,
                        1.0 - codeword, codeword)
    signs = 2.0 * received - 1.0
    at_clip = ldpc.decode(signs * LLR_CLIP, code, 60, 0.8)
    beyond = ldpc.decode(signs * 1000.0, code, 60, 0.8)
    assert bool(at_clip[0]) == bool(beyond[0])
    assert np.array_equal(at_clip[1], beyond[1])
    assert at_clip[2] == beyond[2]
    assert np.array_equal(at_clip[3], beyond[3])


def test_infinite_llrs_are_known_bits_and_a_large_finite_one_is_not():
    code = ldpc.CODES["r0550"]
    rng = np.random.default_rng(31)
    codeword = ldpc.encode(
        rng.integers(0, 2, code.k_bits, dtype=np.uint8), code).astype(
            np.float64)
    llr = (2.0 * codeword - 1.0) * 8.0
    wrong = rng.choice(code.n_bits, size=40, replace=False)
    pinned = llr.copy()
    pinned[wrong] = np.where(codeword[wrong] > 0.5, -np.inf, np.inf)
    finite = llr.copy()
    finite[wrong] = np.where(codeword[wrong] > 0.5, -1e9, 1e9)
    pinned_ok, pinned_hard, pinned_iters, _ = ldpc.decode(
        pinned, code, 60, 0.8)
    finite_ok, finite_hard, finite_iters, _ = ldpc.decode(
        finite, code, 60, 0.8)
    assert (bool(pinned_ok), int(pinned_iters)) == (False, 120)
    assert int((pinned_hard != codeword).sum()) == 146
    assert (bool(finite_ok), int(finite_iters)) == (True, 8)
    assert int((finite_hard != codeword).sum()) == 0


def test_zero_iterations_only_checks_the_syndrome():
    code = ldpc.CODES["r0550"]
    rng = np.random.default_rng(20260829)
    codeword = ldpc.encode(
        rng.integers(0, 2, code.k_bits, dtype=np.uint8), code).astype(
            np.float64)
    noisy = np.where(rng.random(code.n_bits) < 0.05,
                     1.0 - codeword, codeword)
    accepted, hard, n_iters, extrinsic = ldpc.decode(
        (2.0 * noisy - 1.0) * 6.0, code, 0, 0.8)
    assert not accepted and n_iters == 0
    assert np.array_equal(hard, noisy.astype(np.uint8))
    assert not extrinsic.any()


def test_the_min_sum_pass_is_followed_by_a_sum_product_rescue():
    code = ldpc.CODES["r0550"]
    rng = np.random.default_rng(20260829)
    accepted, _hard, n_iters, _extrinsic = ldpc.decode(
        rng.normal(0.0, 3.0, code.n_bits), code, 60, 0.8)
    assert not accepted
    assert n_iters == 120

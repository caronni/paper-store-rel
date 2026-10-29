"""W1c tests for analyzer/mother.py (framing, BP modes, the gate, exposure).

Everything is synthetic and deterministic: no run dir, no pixels, no decode of
a whole sheet.  The measured waterfall these levels sit on is recorded in
`test_measured_waterfall_and_bimodality`.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from holo.receiver.format import tile_codec
from holo.receiver.lib import ldpc
from holo.receiver.lib.ldpc import CODES, LLR_CLIP, LLR_KNOWN

from analyzer import mother as M
from analyzer.types import Exposure

from ._synthetic import (
    R0700,
    R0850,
    build_frame,
    channel_llr,
    through_cells,
)

ALPHA = 0.8


def test_printed_frame_survives_the_cell_round_trip():
    frame = build_frame()
    assert np.array_equal(through_cells(frame), frame.printed)


def test_to_mother_undithers_once_and_shortens():
    frame = build_frame()
    llr = 4.0 * (2.0 * frame.printed.astype(np.float64) - 1.0)
    mother = M.to_mother(llr, frame.row, frame.key, metadata_bit=None)
    code = CODES[mother.rate_id]
    assert mother.active == frame.active == 3400
    assert mother.k_bits == code.k_bits
    assert np.all(np.isneginf(mother.llr[mother.active:mother.k_bits]))
    # The un-dithered mother LLR must agree in sign with the GT codeword on
    # every transmitted position: one dither, in one place.
    signs = mother.llr[mother.transmitted] > 0
    assert np.array_equal(signs, frame.codeword[mother.transmitted] > 0)


def test_to_mother_refuses_a_wrong_length_vector():
    frame = build_frame()
    with pytest.raises(ValueError):
        M.to_mother(np.zeros(100), frame.row, frame.key, metadata_bit=None)


def test_metadata_bit_enters_at_info_index_zero():
    frame = build_frame()
    llr = np.zeros(frame.printed.size)
    right = M.to_mother(llr, frame.row, frame.key,
                        metadata_bit=int(frame.user[0]))
    wrong = M.to_mother(llr, frame.row, frame.key,
                        metadata_bit=1 - int(frame.user[0]))
    assert np.isinf(right.llr[0]) and np.isinf(wrong.llr[0])
    assert (right.llr[0] > 0) == bool(frame.user[0])
    assert (wrong.llr[0] > 0) != bool(frame.user[0])


@pytest.mark.parametrize("ref,rate_error", [(R0850, 0.03), (R0700, 0.06)])
def test_l0_path_certifies_a_clean_enough_frame(ref, rate_error):
    frame = build_frame(ref)
    llr = channel_llr(frame.printed, rate_error, seed=101)
    outcome = tile_codec.cmy8_decode_stream(llr, frame.bank, frame.dither,
                                            60, ALPHA)
    assert outcome[0] is True
    assert np.array_equal(outcome[4], frame.user)


@pytest.mark.parametrize("ref,hard", [(R0850, 0.03), (R0850, 0.06),
                                      (R0700, 0.06), (R0700, 0.10)])
def test_minsum_then_sp_matches_production_bit_for_bit(ref, hard):
    """Catches a missing shortening, a double dither or a sign flip.

    `decode_frame(want_extrinsic=True)` returns the child's extrinsic on the
    transmitted positions in the EXTERNAL sign; our posterior minus the
    clipped channel is the same quantity, so equality here pins the whole
    framing, both when the frame closes and when it fails.
    """
    frame = build_frame(ref)
    llr = channel_llr(frame.printed, hard, seed=202)
    undithered = llr * (1.0 - 2.0 * frame.dither)
    ok, children, _inv, _crc, user, soft = tile_codec.decode_frame(
        undithered, frame.bank, 60, ALPHA, want_extrinsic=True)
    mother = M.to_mother(llr, frame.row, frame.key, metadata_bit=None)
    out = M.bp(mother, None, 60, mode="minsum-then-sp", alpha=ALPHA)
    assert out.syndrome_ok == all(s for _n, s in children)
    assert out.n_iters == sum(n for n, _s in children)
    extrinsic = out.posterior - M.clipped_external(mother.llr)
    assert np.array_equal(extrinsic[mother.transmitted], soft)
    if ok:
        assert np.array_equal(out.hard[:frame.active - 32], user)


def test_posterior_identity_and_agreement_with_ldpc_decode():
    frame = build_frame()
    llr = channel_llr(frame.printed, 0.05, seed=303)
    mother = M.to_mother(llr, frame.row, frame.key, metadata_bit=None)
    out = M.bp(mother, None, 60, mode="minsum-then-sp", alpha=ALPHA)
    syn_ok, hard, n_iters, extrinsic = ldpc.decode(mother.llr,
                                                   CODES[mother.rate_id],
                                                   60, ALPHA)
    assert np.array_equal(out.hard, hard)
    assert out.syndrome_ok == syn_ok and out.n_iters == n_iters
    clipped = M.clipped_external(mother.llr)
    assert np.allclose(out.posterior, clipped + extrinsic, rtol=0, atol=1e-9)
    assert np.array_equal(out.posterior > 0, out.hard == 1)
    assert np.array_equal(out.syndrome, M.syndrome(out.hard,
                                                   CODES[mother.rate_id]))
    assert out.unsat == int(np.count_nonzero(out.syndrome))


def test_sum_product_only_equals_productions_second_pass():
    """`sp` at 60 == the pass `ldpc.decode` runs after min-sum fails."""
    frame = build_frame()
    llr = channel_llr(frame.printed, 0.06, seed=404)
    mother = M.to_mother(llr, frame.row, frame.key, metadata_bit=None)
    minsum = M.bp(mother, None, 60, mode="minsum", alpha=ALPHA)
    assert not minsum.syndrome_ok, "need a frame where min-sum fails"
    undithered = llr * (1.0 - 2.0 * frame.dither)
    _ok, _children, _inv, _crc, _user, soft = tile_codec.decode_frame(
        undithered, frame.bank, 60, ALPHA, want_extrinsic=True)
    sp = M.bp(mother, None, 60, mode="sp", alpha=ALPHA)
    extrinsic = sp.posterior - M.clipped_external(mother.llr)
    assert np.array_equal(extrinsic[mother.transmitted], soft)


@pytest.mark.parametrize("mode,kwargs", [
    ("minsum", {}),
    ("sp", {}),
    ("damped", {"lam": 1.0}),
    ("damped-offset", {"lam": 0.7, "beta": 0.15}),
    ("layered", {}),
])
def test_every_mode_returns_a_consistent_posterior(mode, kwargs):
    frame = build_frame()
    llr = channel_llr(frame.printed, 0.06, seed=505)
    mother = M.to_mother(llr, frame.row, frame.key, metadata_bit=None)
    out = M.bp(mother, None, 30, mode=mode, alpha=ALPHA, **kwargs)
    assert out.mode == mode
    assert np.array_equal(out.posterior > 0, out.hard == 1)
    assert out.unsat == int(np.count_nonzero(out.syndrome))
    assert out.unsat == 0 or not out.syndrome_ok
    # Shortened positions stay pinned at the known zero.
    assert np.all(out.hard[mother.active:mother.k_bits] == 0)


def test_damped_at_lambda_one_reproduces_the_min_sum_branch():
    frame = build_frame()
    llr = channel_llr(frame.printed, 0.05, seed=606)
    mother = M.to_mother(llr, frame.row, frame.key, metadata_bit=None)
    plain = M.bp(mother, None, 25, mode="minsum", alpha=ALPHA)
    damped = M.bp(mother, None, 25, mode="damped", alpha=ALPHA, lam=1.0,
                  beta=0.0)
    assert np.array_equal(plain.hard, damped.hard)
    assert np.allclose(plain.posterior, damped.posterior, rtol=0, atol=1e-9)
    assert plain.n_iters == damped.n_iters


def test_unknown_mode_is_refused():
    frame = build_frame()
    mother = M.to_mother(np.zeros(frame.printed.size), frame.row, frame.key,
                         metadata_bit=None)
    with pytest.raises(ValueError):
        M.bp(mother, None, 5, mode="belief-soup")


def test_pack_h_matches_the_edge_lists_and_is_cached():
    """The packed rows must be the same parity checks the edge lists carry."""
    packed = M.pack_h("r0850")
    code = CODES["r0850"]
    m = code.n_bits - code.k_bits
    assert packed.shape == (m, (code.n_bits + 63) // 64)
    assert M.pack_h("r0850") is packed
    bit_index = np.arange(64, dtype=np.uint64)
    for check in (0, 1, 137, m - 1):
        unpacked = np.concatenate([
            ((word >> bit_index) & np.uint64(1)).astype(np.uint8)
            for word in packed[check]])[:code.n_bits]
        dense = np.zeros(code.n_bits, np.uint8)
        start = int(code.chk_starts[check])
        stop = (code.edge_chk.size if check + 1 == m
                else int(code.chk_starts[check + 1]))
        np.bitwise_xor.at(dense, code.edge_var[start:stop].astype(np.int64),
                          np.uint8(1))
        assert np.array_equal(unpacked, dense)


def test_gate_never_crcs_a_non_codeword_and_counts_distinct():
    frame = build_frame()
    llr = channel_llr(frame.printed, 0.03, seed=707)
    mother = M.to_mother(llr, frame.row, frame.key, metadata_bit=None)
    out = M.bp(mother, None, 60, mode="minsum-then-sp", alpha=ALPHA)
    exposure = Exposure()
    ok, user = M.gate(out.hard, mother, frame.bank, exposure)
    assert ok and np.array_equal(user, frame.user)
    assert exposure.distinct == 1
    # the same codeword again is the same consult
    M.gate(out.hard, mother, frame.bank, exposure)
    assert exposure.distinct == 1
    # a non-codeword never reaches the CRC
    broken = out.hard.copy()
    broken[0] ^= 1
    notes: dict = {}
    ok2, user2 = M.gate(broken, mother, frame.bank, exposure, notes=notes)
    assert (ok2, user2) == (False, None)
    assert notes["refusal"] == "syndrome_failed"
    assert exposure.distinct == 1


def test_exposure_bound_refuses_a_new_consult():
    """Two genuine codewords, a bound that pays for one."""
    frame = build_frame(seed=7)
    other = build_frame(seed=99)
    mother = M.to_mother(np.zeros(frame.printed.size), frame.row, frame.key,
                         metadata_bit=None)
    exposure = Exposure(bound_expected_false=1.5 * 2.0 ** -32)
    assert M.gate(frame.codeword, mother, frame.bank, exposure)[0]
    assert exposure.distinct == 1
    notes: dict = {}
    ok, user = M.gate(other.codeword, mother, other.bank, exposure,
                      notes=notes)
    assert (ok, user) == (False, None)
    assert notes["refusal"] == "exposure_exceeded"
    assert exposure.distinct == 1
    # the already-consulted codeword still passes: it costs nothing new
    assert M.gate(frame.codeword, mother, frame.bank, exposure)[0]


def test_two_workers_at_the_bound_do_not_both_get_through():
    """Review F13, 2026-09-13: the reservation is ONE operation.

    Two genuine codewords, a bound that pays for one, and both workers
    held at the gate's reservation point so they reach it together —
    the interleaving that was legal while `gate` asked "is it new?",
    "would it exceed?" and "add it" separately, and which put the run
    over its bound with two certificates minted.  One is refused now,
    and it is refused for the exposure.
    """
    frame = build_frame(seed=7)
    other = build_frame(seed=99)
    mother = M.to_mother(np.zeros(frame.printed.size), frame.row, frame.key,
                         metadata_bit=None)
    exposure = Exposure(bound_expected_false=1.5 * 2.0 ** -32)
    at_the_gate = threading.Barrier(2, timeout=10)
    reserve = exposure.reserve

    def synchronized(digest):
        at_the_gate.wait()
        return reserve(digest)

    exposure.reserve = synchronized
    notes: list[dict] = [{}, {}]
    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted = list(pool.map(
            lambda pair: M.gate(pair[0].codeword, mother, pair[0].bank,
                                exposure, notes=pair[1])[0],
            [(frame, notes[0]), (other, notes[1])]))

    assert sorted(accepted) == [False, True]
    assert exposure.distinct == 1
    assert not exposure.exceeded()
    refused = notes[accepted.index(False)]
    assert refused["refusal"] == "exposure_exceeded"


def test_a_duplicate_candidate_is_charged_to_one_caller_only():
    """`notes["consulted_new"]` is the rung's own charge; two rungs that
    propose the SAME codeword at the same moment must not both bill for
    it while `distinct` rises by one."""
    frame = build_frame(seed=11)
    mother = M.to_mother(np.zeros(frame.printed.size), frame.row, frame.key,
                         metadata_bit=None)
    exposure = Exposure()
    notes: list[dict] = [{}, {}, {}, {}]
    with ThreadPoolExecutor(max_workers=4) as pool:
        accepted = list(pool.map(
            lambda note: M.gate(frame.codeword, mother, frame.bank,
                                exposure, notes=note)[0], notes))

    assert accepted == [True] * 4
    assert exposure.distinct == 1
    assert sorted(note["consulted_new"] for note in notes) == [0, 0, 0, 1]


def test_gate_refuses_a_bank_that_does_not_match_the_frame():
    frame = build_frame(R0850)
    other = build_frame(R0700)
    mother = M.to_mother(np.zeros(frame.printed.size), frame.row, frame.key,
                         metadata_bit=None)
    with pytest.raises(ValueError):
        M.gate(np.zeros(4096, np.uint8), mother, other.bank, Exposure())


def test_gate_refuses_a_codeword_that_violates_the_shortening():
    """A mother codeword with a non-zero shortened window is not a frame.

    BP cannot make one (the window is pinned at -inf), but a list proposer
    can; it must be refused BEFORE the CRC, so it costs no exposure.
    """
    frame = build_frame(R0850)
    mother = M.to_mother(np.zeros(frame.printed.size), frame.row, frame.key,
                         metadata_bit=None)
    code = CODES[mother.rate_id]
    info = np.zeros(code.k_bits, np.uint8)
    info[:mother.active] = np.concatenate(
        (frame.user, tile_codec.crc32_bits(frame.user)))
    info[mother.active] = 1                      # inside the shortened window
    hard = ldpc.encode(info, code)
    assert not M.syndrome(hard, code).any()      # still a mother codeword
    exposure = Exposure()
    notes: dict = {}
    ok, user = M.gate(hard, mother, frame.bank, exposure, notes=notes)
    assert (ok, user) == (False, None)
    assert notes["refusal"] == "shortening_violated"
    assert exposure.distinct == 0


def test_posterior_summary_is_blind_and_bounded():
    frame = build_frame()
    llr = channel_llr(frame.printed, 0.06, seed=909)
    mother = M.to_mother(llr, frame.row, frame.key, metadata_bit=None)
    out = M.bp(mother, None, 30, mode="minsum-then-sp", alpha=ALPHA)
    summary = M.posterior_summary(out, mother)
    assert summary["n_transmitted"] == frame.printed.size
    assert 0.0 <= summary["fraction_clipped"] <= 1.0
    assert summary["mean_abs_posterior"] >= 0.0
    assert set(summary) == {"mean_abs_posterior", "fraction_clipped",
                            "n_transmitted"}


def test_to_sequential_inverts_the_dither():
    frame = build_frame()
    llr = channel_llr(frame.printed, 0.06, seed=1010)
    mother = M.to_mother(llr, frame.row, frame.key, metadata_bit=None)
    back = M.to_sequential(mother.llr, mother)
    assert np.allclose(back, llr, rtol=0, atol=1e-12)


def test_clipped_external_respects_the_bounded_llr_invariant():
    values = np.array([np.inf, -np.inf, 1e6, -1e6, 3.0])
    out = M.clipped_external(values)
    assert out[0] == LLR_KNOWN and out[1] == -LLR_KNOWN
    assert out[2] == LLR_CLIP and out[3] == -LLR_CLIP and out[4] == 3.0


from __future__ import annotations

import zlib

import numpy as np

from holo3.lib.ldpc import CODES, LLR_CLIP, decode, encode

N_CELLS = 4096
CRC_BITS = 32
PLANE_ORDER: tuple[str, ...] = ("C", "M", "Y")
CMY7_BITS_PER_PACK = 11
CMY7_CELLS_PER_PACK = 4
CMY7_N_CANDIDATES = 1 << CMY7_BITS_PER_PACK
DEMAP_ITERATIONS = 3

Bank = tuple[tuple[str, int], ...]
FrameOutcome = tuple[bool, tuple[tuple[int, bool], ...], bool, bool | None,
                     np.ndarray | None, np.ndarray | None]

_CMY7_RADIX_DIVISORS = np.asarray((7 ** 3, 7 ** 2, 7, 1), dtype=np.int64)
_CMY7_WORDS = np.arange(CMY7_N_CANDIDATES, dtype=np.int64)
CMY7_CODEBOOK = (
    (_CMY7_WORDS[:, None] // _CMY7_RADIX_DIVISORS[None, :]) % 7
).astype(np.uint8)
CMY7_CODEBOOK.setflags(write=False)
_CMY7_BIT_SHIFTS = np.arange(CMY7_BITS_PER_PACK - 1, -1, -1, dtype=np.int64)
_CMY7_CANDIDATE_BITS = (
    (_CMY7_WORDS[:, None] >> _CMY7_BIT_SHIFTS[None, :]) & 1
).astype(bool)
_CMY7_CANDIDATE_BITS.setflags(write=False)
_CMY7_CANDIDATE_BITS_F = _CMY7_CANDIDATE_BITS.astype(np.float64)
_CMY7_CANDIDATE_BITS_F.setflags(write=False)


def states_to_planes(states: np.ndarray) -> np.ndarray:
    s = np.asarray(states).astype(np.uint8, copy=False)
    return ((s[..., None] >> np.arange(3, dtype=np.uint8)) & 1).astype(
        np.uint8)


def planes_to_states(plane_bits: np.ndarray) -> np.ndarray:
    b = np.asarray(plane_bits).astype(np.uint8, copy=False)
    weights = np.asarray((1, 2, 4), dtype=np.uint8)
    return np.sum(b * weights, axis=-1, dtype=np.uint8)


def cmy7_map(bits: np.ndarray) -> np.ndarray:
    b = np.asarray(bits).astype(np.uint8, copy=False)
    powers = (1 << _CMY7_BIT_SHIFTS).astype(np.int64)
    words = np.sum(b.astype(np.int64) * powers, axis=-1, dtype=np.int64)
    return CMY7_CODEBOOK[words].copy()


def cmy7_soft_demap(relative_state_scores: np.ndarray,
                    prior_bit_llrs: np.ndarray | None = None) -> np.ndarray:
    rel = np.asarray(relative_state_scores).astype(np.float64, copy=False)
    prior = (None if prior_bit_llrs is None
             else np.asarray(prior_bit_llrs).astype(np.float64, copy=False))
    scores = np.concatenate(
        (np.zeros(rel.shape[:-1] + (1,), dtype=np.float64), rel), axis=-1)
    metric = np.zeros(rel.shape[:-2] + (CMY7_N_CANDIDATES,),
                      dtype=np.float64)
    for cell in range(CMY7_CELLS_PER_PACK):
        metric += np.take(
            scores[..., cell, :], CMY7_CODEBOOK[:, cell], axis=-1)
    if prior is not None:
        metric += prior @ _CMY7_CANDIDATE_BITS_F.T
    maximum = np.max(metric, axis=-1, keepdims=True)
    with np.errstate(under="ignore"):
        weights = np.exp(metric - maximum)
    one = weights @ _CMY7_CANDIDATE_BITS
    zero = weights @ (~_CMY7_CANDIDATE_BITS)
    with np.errstate(divide="ignore"):
        out = np.log(one) - np.log(zero)
    minimum_safe_sum = (
        (CMY7_N_CANDIDATES // 2) * np.finfo(np.float64).tiny)
    fallback = np.any(
        (one <= minimum_safe_sum) | (zero <= minimum_safe_sum), axis=-1)
    if np.any(fallback):
        metric_rows = metric.reshape(-1, CMY7_N_CANDIDATES)
        out_rows = out.reshape(-1, CMY7_BITS_PER_PACK)
        selected = np.flatnonzero(fallback.reshape(-1))
        fallback_metric = metric_rows[selected]
        with np.errstate(under="ignore"):
            for bit in range(CMY7_BITS_PER_PACK):
                one_mask = _CMY7_CANDIDATE_BITS[:, bit]
                out_rows[selected, bit] = (
                    np.logaddexp.reduce(
                        fallback_metric[:, one_mask], axis=-1)
                    - np.logaddexp.reduce(
                        fallback_metric[:, ~one_mask], axis=-1))
    if prior is not None:
        out -= prior
    return out


def crc32_bits(bits: np.ndarray) -> np.ndarray:
    b = np.packbits(np.asarray(bits, np.uint8)).tobytes()
    c = zlib.crc32(b) & 0xFFFFFFFF
    return ((c >> (31 - np.arange(CRC_BITS))) & 1).astype(np.uint8)


def tile_capacity(rate_id: str, n_sites: int) -> int:
    return CODES[rate_id].k_bits - CRC_BITS - n_sites


def transmitted_positions(code_id: str, shorten: int) -> np.ndarray:
    code = CODES[code_id]
    return np.concatenate((
        np.arange(code.k_bits - shorten, dtype=np.int64),
        np.arange(code.k_bits, code.n_bits, dtype=np.int64)))


def cell_map(site_flat: np.ndarray, a_t: int, b_t: int) -> np.ndarray:
    keep = np.ones(N_CELLS, bool)
    keep[np.asarray(site_flat, np.int64)] = False
    nonsite = np.flatnonzero(keep)
    n_slots = int(nonsite.size)
    j = np.arange(n_slots, dtype=np.int64)
    return nonsite[(a_t * j + b_t) % n_slots]


def encode_tile(user_bits: np.ndarray, rate_id: str, site_flat: np.ndarray,
                a_t: int, b_t: int) -> np.ndarray:
    n_sites = int(np.asarray(site_flat).size)
    cap = tile_capacity(rate_id, n_sites)
    user = np.asarray(user_bits, np.uint8).ravel()
    code = CODES[rate_id]
    info = np.zeros(code.k_bits, np.uint8)
    info[:cap] = user
    info[cap:cap + CRC_BITS] = crc32_bits(user)
    cw = encode(info, code)
    cells = np.zeros(N_CELLS, np.uint8)
    cells[cell_map(site_flat, a_t, b_t)] = cw[
        transmitted_positions(rate_id, n_sites)]
    return cells


def decode_tile(llr_flat: np.ndarray, rate_id: str, site_flat: np.ndarray,
                a_t: int, b_t: int, max_iters: int, alpha: float
                ) -> tuple[bool, np.ndarray | None, int, bool, bool]:
    n_sites = int(np.asarray(site_flat).size)
    cap = tile_capacity(rate_id, n_sites)
    x = np.asarray(llr_flat, np.float64).ravel()
    code = CODES[rate_id]
    llr_code = np.zeros(code.n_bits, dtype=np.float64)
    llr_code[transmitted_positions(rate_id, n_sites)] = \
        x[cell_map(site_flat, a_t, b_t)]
    llr_code[code.k_bits - n_sites:code.k_bits] = -np.inf
    syn_ok, hard, n_iters, _extrinsic = decode(llr_code, code, max_iters,
                                               alpha)
    user = hard[:cap].astype(np.uint8)
    crc_ok = bool(np.array_equal(hard[cap:cap + CRC_BITS], crc32_bits(user)))
    ok = bool(syn_ok and crc_ok)
    return ok, user if ok else None, int(n_iters), bool(syn_ok), crc_ok


def bank_active_bits(bank: Bank) -> int:
    return sum(CODES[code_id].k_bits - shorten for code_id, shorten in bank)


def bank_user_bits(bank: Bank) -> int:
    return bank_active_bits(bank) - CRC_BITS


def bank_transmitted_bits(bank: Bank) -> int:
    return sum(CODES[code_id].n_bits - shorten for code_id, shorten in bank)


def encode_frame(user_bits: np.ndarray, bank: Bank) -> np.ndarray:
    user = np.asarray(user_bits).astype(np.uint8, copy=False).ravel()
    frame = np.concatenate((user, crc32_bits(user)))
    transmitted: list[np.ndarray] = []
    offset = 0
    for code_id, shorten in bank:
        code = CODES[code_id]
        active = code.k_bits - shorten
        info = np.zeros(code.k_bits, dtype=np.uint8)
        info[:active] = frame[offset:offset + active]
        offset += active
        codeword = encode(info, code)
        transmitted.append(codeword[transmitted_positions(code_id, shorten)])
    return np.concatenate(transmitted)


def decode_frame(code_llrs: np.ndarray, bank: Bank, max_iters: int,
                 alpha: float, want_extrinsic: bool = False
                 ) -> FrameOutcome:
    llrs = np.asarray(code_llrs).astype(np.float64, copy=False).ravel()
    children: list[tuple[int, bool]] = []
    active_frames: list[np.ndarray] = []
    extrinsics: list[np.ndarray] = []
    offset = 0
    for code_id, shorten in bank:
        code = CODES[code_id]
        active = code.k_bits - shorten
        n_tx = code.n_bits - shorten
        positions = transmitted_positions(code_id, shorten)
        mother_llr = np.zeros(code.n_bits, dtype=np.float64)
        mother_llr[positions] = llrs[offset:offset + n_tx]
        offset += n_tx
        if shorten:
            mother_llr[active:code.k_bits] = -np.inf
        syndrome_ok, hard, n_iters, extrinsic = decode(mother_llr, code,
                                                       max_iters, alpha)
        if want_extrinsic:
            extrinsics.append(extrinsic[positions])
        children.append((int(n_iters), bool(syndrome_ok)))
        active_frames.append(hard[:active].astype(np.uint8))
    soft = np.concatenate(extrinsics) if want_extrinsic else None
    if not all(syndrome_ok for _n_iters, syndrome_ok in children):
        return False, tuple(children), False, None, None, soft
    frame = np.concatenate(active_frames)
    user = frame[:-CRC_BITS]
    crc_ok = bool(np.array_equal(frame[-CRC_BITS:], crc32_bits(user)))
    return crc_ok, tuple(children), True, crc_ok, (user if crc_ok else None), soft


def cmy7_encode_payload(user_bits: np.ndarray, bank: Bank,
                        interleave_order: np.ndarray,
                        dither_bits: np.ndarray) -> np.ndarray:
    order = np.asarray(interleave_order).astype(np.int64, copy=False)
    dither = np.asarray(dither_bits).astype(np.uint8, copy=False)
    code_bits = encode_frame(user_bits, bank)
    mapped_bits = code_bits[order] ^ dither
    groups = mapped_bits.reshape(-1, CMY7_BITS_PER_PACK)
    return cmy7_map(groups).reshape(-1)


def cmy7_demap_payload(relative_state_scores: np.ndarray,
                       observed_slots: np.ndarray, bank: Bank,
                       interleave_order: np.ndarray,
                       dither_bits: np.ndarray,
                       prior_code_llrs: np.ndarray | None = None
                       ) -> np.ndarray:
    n_code = bank_transmitted_bits(bank)
    n_packs = n_code // CMY7_BITS_PER_PACK
    scores = np.asarray(relative_state_scores).astype(np.float64, copy=False)
    observed = np.asarray(observed_slots).astype(bool, copy=False)
    packs = scores.reshape(n_packs, CMY7_CELLS_PER_PACK, 6).copy()
    complete = observed.reshape(n_packs, CMY7_CELLS_PER_PACK).all(axis=1)
    packs[~complete] = 0.0
    dither = np.asarray(dither_bits).astype(np.uint8, copy=False)
    order = np.asarray(interleave_order).astype(np.int64, copy=False)
    signs = 1.0 - 2.0 * dither
    if prior_code_llrs is None:
        mapped_prior = None
    else:
        prior = np.asarray(prior_code_llrs).astype(np.float64,
                                                   copy=False).ravel()
        mapped_prior = (prior[order] * signs).reshape(
            n_packs, CMY7_BITS_PER_PACK)
    mapped_llrs = cmy7_soft_demap(packs, mapped_prior).reshape(n_code)
    if mapped_prior is not None:
        mapped_llrs.reshape(
            n_packs, CMY7_BITS_PER_PACK)[~complete] = 0.0
    mapped_llrs *= signs
    code_llrs = np.empty(n_code, dtype=np.float64)
    code_llrs[order] = mapped_llrs
    return code_llrs


def cmy7_iterated_decode(code_llrs: np.ndarray,
                         relative_state_scores: np.ndarray,
                         observed_slots: np.ndarray, bank: Bank,
                         interleave_order: np.ndarray,
                         dither_bits: np.ndarray, max_iters: int,
                         alpha: float,
                         demap_iterations: int = DEMAP_ITERATIONS
                         ) -> FrameOutcome:
    outcome = decode_frame(code_llrs, bank, max_iters, alpha,
                           want_extrinsic=demap_iterations > 1)
    if demap_iterations == 1:
        return outcome
    ok, children, crc_invoked, crc_ok, user, soft = outcome
    totals = [n_iters for n_iters, _syndrome_ok in children]
    for index in range(1, demap_iterations):
        if ok or soft is None:
            break
        prior = np.clip(soft, -LLR_CLIP, LLR_CLIP)
        ok, children, crc_invoked, crc_ok, user, soft = decode_frame(
            cmy7_demap_payload(relative_state_scores, observed_slots, bank,
                               interleave_order, dither_bits, prior),
            bank, max_iters, alpha,
            want_extrinsic=index + 1 < demap_iterations)
        for child_index, (n_iters, _syndrome_ok) in enumerate(children):
            totals[child_index] += n_iters
    children = tuple(
        (total, syndrome_ok)
        for (_n_iters, syndrome_ok), total in zip(children, totals,
                                                  strict=True))
    return ok, children, crc_invoked, crc_ok, user, None


def cmy8_encode_payload(user_bits_by_stream: tuple[np.ndarray, ...],
                        banks_by_stream: tuple[Bank, ...],
                        dither_bits_by_stream: tuple[np.ndarray, ...]
                        ) -> np.ndarray:
    n_cells = bank_transmitted_bits(banks_by_stream[0])
    presence = np.empty((n_cells, 3), dtype=np.uint8)
    for plane in range(3):
        dither = np.asarray(dither_bits_by_stream[plane]).astype(
            np.uint8, copy=False)
        presence[:, plane] = encode_frame(
            np.asarray(user_bits_by_stream[plane]),
            banks_by_stream[plane]) ^ dither
    return planes_to_states(presence)


def cmy8_decode_stream(level_llrs: np.ndarray, bank: Bank,
                       dither_bits: np.ndarray, max_iters: int,
                       alpha: float) -> FrameOutcome:
    llrs = np.asarray(level_llrs).astype(np.float64, copy=False)
    dither = np.asarray(dither_bits).astype(np.uint8, copy=False)
    undithered = llrs * (1.0 - 2.0 * dither)
    return decode_frame(undithered, bank, max_iters, alpha)

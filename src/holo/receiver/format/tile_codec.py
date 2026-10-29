from __future__ import annotations

import zlib
from typing import TYPE_CHECKING

import numpy as np

from holo.receiver.lib.ldpc import CODES, LLR_CLIP, decode, encode

if TYPE_CHECKING:
    from .identity import FormatRow

N_CELLS = 4096
CRC_BITS = 32
PLANE_ORDER: tuple[str, ...] = ("C", "M", "Y")
#: 11 bits per 4 cells = 2.75 coded bits/cell, ~97.96% of log2(7).  At
#: p120 the 3,976 payload cells make exactly 994 complete packs = the
#: bank's 10,934 transmitted bits, with no remainder
#: (docs/COLOR-INTEGRATION-DESIGN.md §7.1).
CMY7_BITS_PER_PACK = 11
CMY7_CELLS_PER_PACK = 4
CMY7_N_CANDIDATES = 1 << CMY7_BITS_PER_PACK
#: Adopted at 3 against the pre-registered B7 bar (met at 3, p* 0.015
#: -> 0.0275; NOT met at 2).  On paper, xerox c3-cmy7 771 -> 810
#: certificates, a strict superset, zero lost, close still verified,
#: for ~+45% payload CPU (docs/COLOR-UPLIFT-MEASUREMENTS.md §13.2/§13.5).
DEMAP_ITERATIONS = 3

Bank = tuple[tuple[str, int], ...]
FrameOutcome = tuple[bool, tuple[tuple[int, bool], ...], bool, bool | None,
                     np.ndarray | None, np.ndarray | None]

_CMY7_RADIX_DIVISORS = np.asarray((7 ** 3, 7 ** 2, 7, 1), dtype=np.int64)
_CMY7_WORDS = np.arange(CMY7_N_CANDIDATES, dtype=np.int64)
#: pack7-11x4-v0: an 11-bit MSB-first word as four big-endian base-7
#: digits.  Only 2,048 of the 2,401 tuples are used, so state 7 (CMY)
#: can never be emitted — that is what makes it seven.  The TABLE, not
#: this expression, is the mapper surface; its digest is pinned.
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

#: cmy's alphabet {W, C, M, Y} as presence ids, and its two LABEL
#: streams: hi = [state in {C, M}], lo = [state in {C, Y}], label index
#: (hi << 1) | lo -> W, Y, M, C (cyan is white's antipode).  Copies of
#: holo.core.channel's, under its names (CMY-DESIGN §2.2).
CMY_STATE_IDS: tuple[int, ...] = (0, 1, 2, 4)
CMY_LABEL_STREAMS: tuple[str, ...] = ("hi", "lo")
CMY_LABEL_TO_STATE: tuple[int, ...] = (0, 4, 2, 1)
_CMY_STATE_TO_LABEL = np.full(8, -1, dtype=np.int8)
_CMY_STATE_TO_LABEL[np.asarray(CMY_LABEL_TO_STATE)] = np.arange(
    len(CMY_LABEL_TO_STATE), dtype=np.int8)
_CMY_STATE_TO_LABEL.setflags(write=False)


def states_to_planes(states: np.ndarray) -> np.ndarray:
    s = np.asarray(states).astype(np.uint8, copy=False)
    return ((s[..., None] >> np.arange(3, dtype=np.uint8)) & 1).astype(
        np.uint8)


def planes_to_states(plane_bits: np.ndarray) -> np.ndarray:
    b = np.asarray(plane_bits).astype(np.uint8, copy=False)
    weights = np.asarray((1, 2, 4), dtype=np.uint8)
    return np.sum(b * weights, axis=-1, dtype=np.uint8)


#: The row's alphabet as presence bits, (n_states, 3) in C, M, Y order.
def plane_bits(row: FormatRow) -> np.ndarray:
    return states_to_planes(np.asarray(row.state_ids, dtype=np.uint8))


#: Each alphabet state's bit on each of the row's per-cell streams,
#: (n_states, n_streams): a toner stream reads its plane's presence
#: bit, a label stream its bit of the state's label.  Derived from the
#: row, never typed out; K and cmy7 carry no per-cell stream bit.
def stream_bits(row: FormatRow) -> np.ndarray:
    states = np.asarray(row.state_ids, dtype=np.uint8)
    planes = states_to_planes(states)
    labels = _CMY_STATE_TO_LABEL[states]
    shift = len(CMY_LABEL_STREAMS) - 1
    columns = [
        planes[:, fact.plane_index] if fact.label_index is None
        else (labels >> (shift - fact.label_index)) & 1
        for fact in row.streams]
    return np.stack(columns, axis=1).astype(np.uint8)


#: The planes whose presence bits SUM to a per-cell stream's bit over
#: the row's alphabet, the stream at `column`: a cmy8 toner stream its
#: own plane, a cmy label stream its two toners (hi C, M; lo C, Y) --
#: exact, since a cmy cell carries at most one toner.  () for a stream
#: with no per-cell bit (K's and cmy7's main, no dither aux); a stream
#: whose bit is no such sum raises.
def stream_toners(row: FormatRow, column: int) -> tuple[int, ...]:
    if row.streams[column].dither_aux is None:
        return ()
    planes = plane_bits(row).astype(np.int64)
    bits = stream_bits(row)[:, column].astype(np.int64)
    singles = np.flatnonzero((planes.sum(axis=1) == 1) & (bits == 1))
    toners = tuple(sorted(int(np.flatnonzero(planes[state])[0])
                          for state in singles))
    if not np.array_equal(planes[:, list(toners)].sum(axis=1), bits):
        raise ValueError(f"stream {row.streams[column].stream_id!r} is no "
                         f"sum of toner presences over {row.state_ids}")
    return toners


def cmy7_map(bits: np.ndarray) -> np.ndarray:
    b = np.asarray(bits).astype(np.uint8, copy=False)
    powers = (1 << _CMY7_BIT_SHIFTS).astype(np.int64)
    words = np.sum(b.astype(np.int64) * powers, axis=-1, dtype=np.int64)
    return CMY7_CODEBOOK[words].copy()


#: The prior is folded into every candidate's metric and then
#: SUBTRACTED, so the return stays EXTRINSIC.  Because the codebook
#: realizes all 2,048 patterns, a prior alone factorizes exactly and
#: an unobserved pack's extrinsic is zero — that keeps erased packs silent.
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
    # Each marginal sums 1,024 candidate weights, so the dense fast path
    # is kept only while both partitions are comfortably normal; near the
    # subnormal frontier a sum can stay positive while losing all
    # precision, so those rows fall back to a row-local logaddexp.
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


#: MSB-first packbits, last byte zero-padded, zlib.crc32 — ported
#: exactly from paperholo's _crc32_bits.  The default packbits bit
#: order IS the format's; an LSB-first spelling here is a fork
#: (conversion_docs/03-keystream-metadata.md:61-67).
def crc32_bits(bits: np.ndarray) -> np.ndarray:
    b = np.packbits(np.asarray(bits, np.uint8)).tobytes()
    c = zlib.crc32(b) & 0xFFFFFFFF
    return ((c >> (31 - np.arange(CRC_BITS))) & 1).astype(np.uint8)


def tile_capacity(rate_id: str, n_sites: int) -> int:
    return CODES[rate_id].k_bits - CRC_BITS - n_sites


#: Shortening consumes the INFO TAIL only — parity is always
#: transmitted.  That is the paperholo convention, and it is
#: load-bearing: colocation gives every tile the same site count, so
#: there are no degenerate tiles and no overflow into parity.
def transmitted_positions(code_id: str, shorten: int) -> np.ndarray:
    code = CODES[code_id]
    return np.concatenate((
        np.arange(code.k_bits - shorten, dtype=np.int64),
        np.arange(code.k_bits, code.n_bits, dtype=np.int64)))


#: a_t must be coprime to n_slots or this is not a bijection — v1
#: asserted it here; holo3 relies on keystream.slot_perm_params having
#: drawn it that way.  The affine map breaks the tile-invariant shorten
#: pattern (conversion_docs/04-format-identity.md §I, :266-271).
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


#: Shortened info-tail positions enter as -inf (KNOWN zero), not 0.0
#: (erasure).  ok requires BOTH the syndrome and the CRC: a
#: syndrome-only pass is not a certificate
#: (F9 certification discipline, conversion_docs/02-ldpc.md).
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


#: At demap_iterations == 1 this is EXACTLY decode_frame on the
#: caller's first demap, byte for byte — that null is what makes the
#: iterated arm provable.  Per-child n_iters are the SUM over inner
#: decodes, so an attempt record still measures the whole attempt.
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


#: One cmy stream's label-bit LLRs from (..., 3) state scores: columns
#: C, M, Y relative to W's implicit zero; stream 0 is hi, 1 is lo.
#: Without the sibling's label bits the exact marginal, with them the
#: conditional.  LABEL-bit LLRs: a codeword bit's flips where the
#: stream's dither is 1.  The copy of holo.core.channel's.
def cmy_soft_demap(scores: np.ndarray, stream: int,
                   sibling_label_bits: np.ndarray | None = None
                   ) -> np.ndarray:
    if isinstance(stream, bool) or stream not in (0, 1):
        raise ValueError(f"stream {stream!r} is neither 0 (hi) nor 1 (lo)")
    rel = np.asarray(scores).astype(np.float64, copy=False)
    s_c, s_m, s_y = rel[..., 0], rel[..., 1], rel[..., 2]
    if sibling_label_bits is None:
        zero = np.zeros_like(s_c)
        if stream == 0:
            return np.logaddexp(s_c, s_m) - np.logaddexp(zero, s_y)
        return np.logaddexp(s_c, s_y) - np.logaddexp(zero, s_m)
    sibling = np.asarray(sibling_label_bits)
    if stream == 0:
        return np.where(sibling == 1, s_c - s_y, s_m)
    return np.where(sibling == 1, s_c - s_m, s_y)


def cmy8_decode_stream(level_llrs: np.ndarray, bank: Bank,
                       dither_bits: np.ndarray, max_iters: int,
                       alpha: float) -> FrameOutcome:
    llrs = np.asarray(level_llrs).astype(np.float64, copy=False)
    dither = np.asarray(dither_bits).astype(np.uint8, copy=False)
    undithered = llrs * (1.0 - 2.0 * dither)
    return decode_frame(undithered, bank, max_iters, alpha)

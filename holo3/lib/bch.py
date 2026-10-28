from __future__ import annotations

import numpy as np

GF_PRIM_POLY: int = 0x89
N_FULL: int = 127
K_FULL: int = 50
T: int = 13
D_MIN: int = 27
SHORTEN_BY: int = 27
N_WORD: int = N_FULL - SHORTEN_BY
K_MSG: int = K_FULL - SHORTEN_BY
N_PARITY: int = N_FULL - K_FULL

_M: int = 7
_ORDER: int = (1 << _M) - 1


def _build_gf_tables() -> tuple[np.ndarray, np.ndarray]:
    exp = np.zeros(_ORDER, dtype=np.uint8)
    log = np.zeros(_ORDER + 1, dtype=np.int64)
    x = 1
    for i in range(_ORDER):
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & 0x80:
            x ^= GF_PRIM_POLY
    return exp, log


_EXP, _LOG = _build_gf_tables()
_EXP_LIST: list[int] = [int(v) for v in _EXP]
_LOG_LIST: list[int] = [int(v) for v in _LOG]


def _polymod2(a_bits: int, g_bits: int) -> int:
    gdeg = g_bits.bit_length() - 1
    while a_bits.bit_length() - 1 >= gdeg and a_bits:
        a_bits ^= g_bits << (a_bits.bit_length() - 1 - gdeg)
    return a_bits


def _cyclotomic_root_set() -> set[int]:
    roots: set[int] = set()
    for r in range(1, 2 * T + 1):
        c = r
        while c not in roots:
            roots.add(c)
            c = (2 * c) % _ORDER
    return roots


def _build_generator_poly() -> np.ndarray:
    g = [1]
    for r in sorted(_cyclotomic_root_set()):
        ar = _EXP_LIST[r % _ORDER]
        new = [0] * (len(g) + 1)
        for i, gi in enumerate(g):
            if gi:
                new[i + 1] ^= gi
                new[i] ^= _EXP_LIST[(_LOG_LIST[gi] + _LOG_LIST[ar]) % _ORDER]
        g = new
    return np.asarray(g, dtype=np.uint8)


_GPOLY: np.ndarray = _build_generator_poly()
_GPOLY_INT: int = sum(int(c) << i for i, c in enumerate(_GPOLY))


def generator_poly() -> np.ndarray:
    return _GPOLY.copy()


def encode(message_bits: np.ndarray) -> np.ndarray:
    m = np.asarray(message_bits, dtype=np.uint8)
    m_int = 0
    for j in range(K_MSG):
        if m[j]:
            m_int |= 1 << j
    parity = _polymod2(m_int << N_PARITY, _GPOLY_INT)
    word = np.zeros(N_WORD, dtype=np.uint8)
    for i in range(N_PARITY):
        word[i] = (parity >> i) & 1
    word[N_PARITY:] = m
    return word


def message_from_word(word_bits: np.ndarray) -> np.ndarray:
    w = np.asarray(word_bits, dtype=np.uint8)
    return w[N_PARITY:].copy()


def _build_synd_matrix() -> np.ndarray:
    j = np.arange(1, 2 * T + 1, dtype=np.int64)[:, None]
    i = np.arange(N_WORD, dtype=np.int64)[None, :]
    return _EXP[(j * i) % _ORDER]


_SYND_MATRIX: np.ndarray = _build_synd_matrix()


def syndromes(word_bits: np.ndarray) -> np.ndarray:
    w = np.asarray(word_bits, dtype=np.uint8)
    idx = np.flatnonzero(w)
    if idx.size == 0:
        return np.zeros(2 * T, dtype=np.uint8)
    return np.bitwise_xor.reduce(_SYND_MATRIX[:, idx], axis=1)


def _syndromes_many_words(words: np.ndarray) -> np.ndarray:
    out = np.empty((words.shape[0], 2 * T), dtype=np.uint8)
    for lower in range(0, words.shape[0], 4096):
        block = words[lower:lower + 4096]
        products = block[:, None, :] * _SYND_MATRIX[None, :, :]
        out[lower:lower + block.shape[0]] = np.bitwise_xor.reduce(
            products, axis=2
        )
    return out


def syndromes_many(words_bits: np.ndarray) -> np.ndarray:
    return _syndromes_many_words(
        np.asarray(words_bits).astype(np.uint8, copy=False))


def _berlekamp_massey(synd: list[int]) -> tuple[list[int], int]:
    c_poly = [1]
    b_poly = [1]
    lfsr_len = 0
    shift = 1
    b_disc = 1
    for n, s_n in enumerate(synd):
        d = s_n
        for i in range(1, min(lfsr_len, len(c_poly) - 1) + 1):
            ci, sj = c_poly[i], synd[n - i]
            if ci and sj:
                d ^= _EXP_LIST[(_LOG_LIST[ci] + _LOG_LIST[sj]) % _ORDER]
        if d == 0:
            shift += 1
            continue
        coef_log = (_LOG_LIST[d] - _LOG_LIST[b_disc]) % _ORDER
        need = len(b_poly) + shift
        if 2 * lfsr_len <= n:
            prev = c_poly[:]
            if len(c_poly) < need:
                c_poly += [0] * (need - len(c_poly))
            for i, bi in enumerate(b_poly):
                if bi:
                    c_poly[i + shift] ^= _EXP_LIST[
                        (coef_log + _LOG_LIST[bi]) % _ORDER]
            lfsr_len = n + 1 - lfsr_len
            b_poly = prev
            b_disc = d
            shift = 1
        else:
            if len(c_poly) < need:
                c_poly += [0] * (need - len(c_poly))
            for i, bi in enumerate(b_poly):
                if bi:
                    c_poly[i + shift] ^= _EXP_LIST[
                        (coef_log + _LOG_LIST[bi]) % _ORDER]
            shift += 1
    while len(c_poly) > 1 and c_poly[-1] == 0:
        c_poly.pop()
    return c_poly, lfsr_len


def _build_chien_pow_matrix() -> np.ndarray:
    i = np.arange(_ORDER, dtype=np.int64)[:, None]
    j = np.arange(2 * T + 1, dtype=np.int64)[None, :]
    return (-(i * j)) % _ORDER


_CHIEN_POW: np.ndarray = _build_chien_pow_matrix()


def _chien_roots(sigma: list[int]) -> np.ndarray:
    vals = np.zeros(_ORDER, dtype=np.uint8)
    for j, cj in enumerate(sigma):
        if cj:
            vals ^= _EXP[(int(_LOG[cj]) + _CHIEN_POW[:, j]) % _ORDER]
    return np.flatnonzero(vals == 0)


def _decode_syndromes(word: np.ndarray,
                      synd: np.ndarray) -> tuple[np.ndarray, int] | None:
    if not synd.any():
        return word.copy(), 0
    sigma, lfsr_len = _berlekamp_massey([int(s) for s in synd])
    if lfsr_len > T or len(sigma) - 1 != lfsr_len:
        return None
    pos = _chien_roots(sigma)
    if pos.size != lfsr_len or bool((pos >= N_WORD).any()):
        return None
    corrected = word.copy()
    corrected[pos] ^= 1
    if syndromes(corrected).any():
        return None
    return corrected, int(lfsr_len)


def decode(word_bits: np.ndarray) -> tuple[np.ndarray, int] | None:
    w = np.asarray(word_bits, dtype=np.uint8)
    return _decode_syndromes(w, syndromes(w))


def decode_erasures(word_bits: np.ndarray,
                    erasure_idx: np.ndarray) -> tuple[np.ndarray, int] | None:
    w = np.asarray(word_bits, dtype=np.uint8)
    era = np.unique(np.asarray(erasure_idx, dtype=np.int64))
    f = int(era.size)
    if f > 2 * T:
        return None
    if f == 0:
        return decode(w)
    keep = np.ones(N_WORD, dtype=bool)
    keep[era] = False
    best: tuple[np.ndarray, int] | None = None
    for fill in (0, 1):
        trial = w.copy()
        trial[era] = fill
        res = _decode_syndromes(trial, syndromes(trial))
        if res is None:
            continue
        corrected, _ = res
        e_out = int(np.sum(corrected[keep] != w[keep]))
        if 2 * e_out + f > 2 * T:
            continue
        if best is None or e_out < best[1]:
            best = (corrected, e_out)
    return best


CHIEN_BLOCK_ROWS: int = 4096

_EXP2: np.ndarray = np.concatenate([_EXP, _EXP])
_LOG16: np.ndarray = _LOG.astype(np.int16)
_CHIEN_POW16: np.ndarray = _CHIEN_POW.astype(np.int16)
_POISON: int = 2 * _ORDER
_EXPZ: np.ndarray = np.concatenate(
    [_EXP2, np.zeros(512 - _EXP2.size, np.uint8)])
_LOGZ: np.ndarray = _LOG16.copy()
_LOGZ[0] = _POISON
_SIGMA_WIDTH: int = T + 1
_POW_COLUMNS: np.ndarray = np.ascontiguousarray(
    _CHIEN_POW16[:, :_SIGMA_WIDTH].T)
_BM_WIDTH: int = 2 * T + 1


def berlekamp_massey_many(
    syndrome_rows: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows = np.asarray(syndrome_rows, np.uint8)
    height = rows.shape[0]
    sigma = np.zeros((height, _BM_WIDTH), np.uint8)
    sigma[:, 0] = 1
    auxiliary = np.zeros((height, 2 * _BM_WIDTH), np.uint8)
    auxiliary[:, _BM_WIDTH] = 1
    sigma_len = np.ones(height, np.int16)
    auxiliary_len = np.ones(height, np.int16)
    lfsr_len = np.zeros(height, np.int16)
    shift = np.ones(height, np.int16)
    b_disc = np.ones(height, np.uint8)
    synd_log = _LOGZ[rows]
    lane = np.arange(height, dtype=np.int64)[:, None]
    column = np.arange(_BM_WIDTH, dtype=np.int16)
    padded = column + np.int16(_BM_WIDTH)

    for step in range(0, 2 * T, 2):
        discrepancy = rows[:, step].copy()
        if step:
            index = _LOGZ[sigma[:, 1:step + 1]] + synd_log[:, step - 1::-1]
            index = np.where(
                column[1:step + 1] <= np.minimum(lfsr_len,
                                                 sigma_len - 1)[:, None],
                index, np.int16(_POISON))
            discrepancy ^= np.bitwise_xor.reduce(_EXPZ[index], axis=1)
        nonzero = discrepancy != 0
        change = nonzero & (2 * lfsr_len <= step)
        if nonzero.any():
            need = auxiliary_len + shift
            scale = np.where(
                nonzero,
                (_LOGZ[discrepancy] - _LOGZ[b_disc]) % _ORDER,
                _POISON).astype(np.int16)
            taken = auxiliary[lane, padded[None, :] - shift[:, None]]
            previous, previous_len = sigma.copy(), sigma_len.copy()
            sigma ^= _EXPZ[scale[:, None] + _LOGZ[taken]]
            sigma_len = np.where(nonzero, np.maximum(sigma_len, need),
                                 sigma_len).astype(np.int16)
            grown = (step + 1 - lfsr_len).astype(np.int16)
            auxiliary[:, _BM_WIDTH:] = np.where(
                change[:, None], previous, auxiliary[:, _BM_WIDTH:])
            auxiliary_len = np.where(change, previous_len,
                                     auxiliary_len).astype(np.int16)
            b_disc = np.where(change, discrepancy, b_disc)
            lfsr_len = np.where(change, grown, lfsr_len).astype(np.int16)
        shift = np.where(change, np.int16(2), shift + 2).astype(np.int16)

    live = (sigma != 0) & (column[None, :] < sigma_len[:, None])
    trimmed = _BM_WIDTH - np.argmax(live[:, ::-1], axis=1)
    return sigma, trimmed.astype(np.int64), lfsr_len.astype(np.int64)


def chien_root_mask(sigma_rows: np.ndarray) -> np.ndarray:
    rows = np.asarray(sigma_rows, np.uint8)
    mask = np.empty((rows.shape[0], N_FULL), dtype=bool)
    for lower in range(0, rows.shape[0], CHIEN_BLOCK_ROWS):
        block = rows[lower:lower + CHIEN_BLOCK_ROWS]
        logs = _LOG16[block]
        live = (block != 0)
        values = np.zeros((block.shape[0], N_FULL), dtype=np.uint8)
        for j in range(_SIGMA_WIDTH):
            col = live[:, j]
            if not col.any():
                continue
            term = _EXP2[logs[:, j, None] + _POW_COLUMNS[None, j, :]]
            values ^= term * col[:, None].astype(np.uint8)
        mask[lower:lower + block.shape[0]] = values == 0
    return mask


def decode_many(
    words_bits: np.ndarray,
) -> list[tuple[np.ndarray, int] | None]:
    words = np.asarray(words_bits).astype(np.uint8, copy=False)
    height = words.shape[0]
    out: list[tuple[np.ndarray, int] | None] = [None] * height
    if height == 0:
        return out
    synds = _syndromes_many_words(words)
    dirty = synds.any(axis=1)
    for index in np.flatnonzero(~dirty):
        out[int(index)] = (words[index].copy(), 0)
    dirty_rows = np.flatnonzero(dirty)
    if dirty_rows.size == 0:
        return out
    sigma, trimmed, lengths = berlekamp_massey_many(synds[dirty_rows])
    kept = (lengths <= T) & (trimmed - 1 == lengths)
    survivors = dirty_rows[kept]
    if survivors.size == 0:
        return out
    degrees = lengths[kept]
    coefficients = sigma[kept, :_SIGMA_WIDTH]
    roots = chien_root_mask(coefficients)
    accepted = np.flatnonzero(
        (roots.sum(axis=1) == degrees) & ~roots[:, N_WORD:].any(axis=1))
    if accepted.size == 0:
        return out
    rows = survivors[accepted]
    corrected = words[rows] ^ roots[accepted, :N_WORD].astype(np.uint8)
    clean = ~_syndromes_many_words(corrected).any(axis=1)
    for slot in np.flatnonzero(clean).tolist():
        out[int(rows[slot])] = (corrected[slot].copy(),
                                int(degrees[accepted[slot]]))
    return out

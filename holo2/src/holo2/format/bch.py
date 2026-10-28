"""Shortened binary BCH word code over GF(2^7) — BCH(127,50,t=13) -> (100,23).

CARRIED VERBATIM (holo2 firewall: copy-and-adapt, never import) from
``src/holo/core/bch.py``.  Every executable line below is the original;
only this paragraph is new.  The code is FORMAT-AXIS — a changed bit here
stops printed sheets decoding — and the carry is pinned character for
character by ``tests/holo2_oracles/test_oracle_tiles.py``.

FORMAT-AXIS (HOLO-DESIGN §4.3, decision F3). The pilot address-word code:
narrow-sense BCH over GF(2^7) with primitive polynomial 0x89 = x^7 + x^3 + 1,
roots alpha^1..alpha^26 (11 cyclotomic cosets: C1,C3,C5,C7,C9,C11,C13,C15,
C19,C21,C23 — C17==C9 and C25==C19 fold in), generator degree 77, designed
distance d >= 27, shortened by 27 to a transmitted word of 100 bits carrying
a 23-bit message.

PROVENANCE: ported from src/paperholo/bch.py (the layout_version-3 instance,
CODE_V3, frozen 2026-07-08 by the v3 migration contract). g(x) is identical,
so holo words are BYTE-COMPATIBLE with paperholo v3/v4 words: same message
bits -> same 100 transmitted bits (value scrambling, which differs between
the formats, lives outside this module). The v2-format (127,64,t=10) instance
and its 36/37-bit message paths are deliberately NOT ported.

Message semantics: holo v1 messages are 23 bits = [18-bit counter][5 zero
pads], but this codec is generic over any 23-bit message — pad enforcement
(the 2^-5 cold gate) lives in the format layer, never here.

Conventions:
- A word is a uint8 bit array; index i = coefficient of x^i of the code
  polynomial. Full codewords have degree <= 126; the 27 SHORTENED positions
  are the highest-order information positions x^100..x^126, fixed 0 and
  never transmitted. Transmitted words are the 100 coefficients x^0..x^99.
- Systematic: message bit j sits at position N_PARITY + j; positions
  0..N_PARITY-1 carry the parity remainder (N_PARITY = 77 = deg g).
- g(x) is DERIVED (from the cyclotomic root set), never stored; the golden
  test pins its sha256.
- decode() is errors-only at full strength t=13 — no caller-supplied
  max_errors anywhere in this module. decode_erasures() enforces
  2e + f <= 26 INSIDE the decoder (the e022 v2.1 bug class: a weaker
  caller-passed budget once silently disabled erasure fills; holo removes
  the knob entirely).
- syndromes_many()/decode_many() are exact row-batched execution paths: the
  initial syndrome screen is vectorized, while BM, Chien, shortening refusal,
  and final verification are the same routines as scalar decode().

Self-contained: numpy + stdlib only.
"""
from __future__ import annotations

import numpy as np

GF_PRIM_POLY: int = 0x89   # x^7 + x^3 + 1, primitive over GF(2^7); frozen
N_FULL: int = 127          # full code length = 2^7 - 1
K_FULL: int = 50           # full-code dimension
T: int = 13                # correction radius (errors-only)
D_MIN: int = 27            # designed distance (2*T + 1)
SHORTEN_BY: int = 27       # high-order info positions fixed 0
N_WORD: int = N_FULL - SHORTEN_BY    # 100 transmitted bits
K_MSG: int = K_FULL - SHORTEN_BY     # 23 message bits
N_PARITY: int = N_FULL - K_FULL      # 77 = deg g(x)

_M = 7
_ORDER = (1 << _M) - 1     # 127, multiplicative order of GF(2^7)*

_cache: dict[str, object] = {}


# ---------------------------------------------------------------- GF(2^7)

def gf_tables() -> tuple[np.ndarray, np.ndarray]:
    """(exp, log) tables for GF(2^7): exp[i] = alpha^i (i in 0..126, uint8),
    log[alpha^i] = i (log[0] unused, int64). Cached; treat as read-only."""
    if "tables" not in _cache:
        exp = np.zeros(_ORDER, dtype=np.uint8)
        log = np.zeros(_ORDER + 1, dtype=np.int64)
        x = 1
        for i in range(_ORDER):
            exp[i] = x
            log[x] = i
            x <<= 1
            if x & 0x80:
                x ^= GF_PRIM_POLY
        assert x == 1, "0x89 must be primitive over GF(2^7)"
        _cache["tables"] = (exp, log)
    return _cache["tables"]  # type: ignore[return-value]


def _tables_list() -> tuple[list[int], list[int]]:
    """Python-list mirror of gf_tables() for scalar-heavy loops (BM)."""
    if "tables_list" not in _cache:
        exp, log = gf_tables()
        _cache["tables_list"] = ([int(v) for v in exp], [int(v) for v in log])
    return _cache["tables_list"]  # type: ignore[return-value]


def _polymod2(a_bits: int, g_bits: int) -> int:
    """Remainder of GF(2) polynomial division (bit i = coeff of x^i)."""
    gdeg = g_bits.bit_length() - 1
    while a_bits.bit_length() - 1 >= gdeg and a_bits:
        a_bits ^= g_bits << (a_bits.bit_length() - 1 - gdeg)
    return a_bits


def _as_word(word_bits: np.ndarray, n_bits: int) -> np.ndarray:
    w = np.asarray(word_bits)
    if w.shape != (n_bits,):
        raise ValueError(f"expected shape ({n_bits},), got {w.shape}")
    w = w.astype(np.uint8)
    if not np.isin(w, (0, 1)).all():
        raise ValueError("bits must be 0/1")
    return w


def _as_words(words_bits: np.ndarray, n_bits: int) -> np.ndarray:
    """The row-batched counterpart of :func:`_as_word`."""
    words = np.asarray(words_bits)
    if words.ndim != 2 or words.shape[1] != n_bits:
        raise ValueError(f"expected (H, {n_bits}), got {words.shape}")
    words = words.astype(np.uint8)
    if not np.isin(words, (0, 1)).all():
        raise ValueError("bits must be 0/1")
    return words


# ---------------------------------------------------------------- generator

def _cyclotomic_root_set() -> set[int]:
    """Union of the 2-cyclotomic cosets mod 127 containing 1..2T."""
    roots: set[int] = set()
    for r in range(1, 2 * T + 1):
        c = r
        while c not in roots:
            roots.add(c)
            c = (2 * c) % _ORDER
    return roots


def generator_poly() -> np.ndarray:
    """g(x) coefficients ascending (index = power of x), (78,) uint8,
    degree 77. Derived from the root set every first call — never stored
    as literals (the golden test pins its sha256)."""
    if "gpoly" not in _cache:
        exp_l, log_l = _tables_list()
        g = [1]  # coefficients in GF(2^7); they collapse to {0,1} at the end
        for r in sorted(_cyclotomic_root_set()):
            ar = exp_l[r % _ORDER]
            # g(x) *= (x + alpha^r)
            new = [0] * (len(g) + 1)
            for i, gi in enumerate(g):
                if gi:
                    new[i + 1] ^= gi
                    new[i] ^= exp_l[(log_l[gi] + log_l[ar]) % _ORDER]
            g = new
        assert len(g) - 1 == N_PARITY, f"deg g = {len(g) - 1}, expected {N_PARITY}"
        assert all(c in (0, 1) for c in g), "g(x) must be binary"
        assert g[0] == 1 and g[N_PARITY] == 1
        _cache["gpoly"] = np.asarray(g, dtype=np.uint8)
        _cache["gpoly_int"] = sum(c << i for i, c in enumerate(g))
    return _cache["gpoly"].copy()  # type: ignore[union-attr]


def _gpoly_int() -> int:
    if "gpoly_int" not in _cache:
        generator_poly()
    return _cache["gpoly_int"]  # type: ignore[return-value]


# ---------------------------------------------------------------- encode

def encode(message_bits: np.ndarray) -> np.ndarray:
    """Systematic encode: (23,) message bits -> (100,) transmitted word."""
    m = _as_word(message_bits, K_MSG)
    m_int = 0
    for j in range(K_MSG):
        if m[j]:
            m_int |= 1 << j
    parity = _polymod2(m_int << N_PARITY, _gpoly_int())
    word = np.zeros(N_WORD, dtype=np.uint8)
    for i in range(N_PARITY):
        word[i] = (parity >> i) & 1
    word[N_PARITY:] = m
    return word


def message_from_word(word_bits: np.ndarray) -> np.ndarray:
    """(100,) transmitted word -> (23,) systematic message bits."""
    w = _as_word(word_bits, N_WORD)
    return w[N_PARITY:].copy()


# ---------------------------------------------------------------- syndromes

def _synd_matrix() -> np.ndarray:
    """A[j-1, i] = alpha^(j*i), j in 1..2T, i in 0..99. (26, 100) uint8."""
    if "synd_matrix" not in _cache:
        exp, _ = gf_tables()
        j = np.arange(1, 2 * T + 1)[:, None]
        i = np.arange(N_WORD)[None, :]
        _cache["synd_matrix"] = exp[(j * i) % _ORDER]
    return _cache["synd_matrix"]  # type: ignore[return-value]


def syndromes(word_bits: np.ndarray) -> np.ndarray:
    """S_j = w(alpha^j) for j = 1..26 -> (26,) uint8 GF elements."""
    w = _as_word(word_bits, N_WORD)
    idx = np.flatnonzero(w)
    if idx.size == 0:
        return np.zeros(2 * T, dtype=np.uint8)
    return np.bitwise_xor.reduce(_synd_matrix()[:, idx], axis=1)


def _syndromes_many_words(words: np.ndarray) -> np.ndarray:
    """Vectorized syndrome kernel for already validated word rows.

    The 4096-row blocks are the proven paperholo implementation's bounded
    working set, not a hypothesis limit: every input row is processed and
    returned in its original order.
    """
    matrix = _synd_matrix()
    out = np.empty((words.shape[0], 2 * T), dtype=np.uint8)
    for lower in range(0, words.shape[0], 4096):
        block = words[lower:lower + 4096]
        # Multiplication is exact selection because each input is binary;
        # reduction is GF(2^7) addition (bitwise XOR).
        products = block[:, None, :] * matrix[None, :, :]
        out[lower:lower + block.shape[0]] = np.bitwise_xor.reduce(
            products, axis=2
        )
    return out


def syndromes_many(words_bits: np.ndarray) -> np.ndarray:
    """Syndromes for ``(H, 100)`` words, returned as ``(H, 26)``.

    This is exactly :func:`syndromes` row by row, with the expensive initial
    screen evaluated in vectorized blocks.  Empty batches are supported.
    """
    return _syndromes_many_words(_as_words(words_bits, N_WORD))


# ---------------------------------------------------------------- decode

def _berlekamp_massey(synd: list[int]) -> tuple[list[int], int]:
    """BM over GF(2^7); returns (sigma coeffs ascending trimmed, L)."""
    exp_l, log_l = _tables_list()
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
                d ^= exp_l[(log_l[ci] + log_l[sj]) % _ORDER]
        if d == 0:
            shift += 1
            continue
        coef_log = (log_l[d] - log_l[b_disc]) % _ORDER
        need = len(b_poly) + shift
        if 2 * lfsr_len <= n:
            prev = c_poly[:]
            if len(c_poly) < need:
                c_poly += [0] * (need - len(c_poly))
            for i, bi in enumerate(b_poly):
                if bi:
                    c_poly[i + shift] ^= exp_l[(coef_log + log_l[bi]) % _ORDER]
            lfsr_len = n + 1 - lfsr_len
            b_poly = prev
            b_disc = d
            shift = 1
        else:
            if len(c_poly) < need:
                c_poly += [0] * (need - len(c_poly))
            for i, bi in enumerate(b_poly):
                if bi:
                    c_poly[i + shift] ^= exp_l[(coef_log + log_l[bi]) % _ORDER]
            shift += 1
    while len(c_poly) > 1 and c_poly[-1] == 0:
        c_poly.pop()
    return c_poly, lfsr_len


def _chien_pow_matrix() -> np.ndarray:
    """P[i, j] = (-i*j) mod 127 for i in 0..126, j in 0..2T. int64."""
    if "chien_pow" not in _cache:
        i = np.arange(_ORDER)[:, None]
        j = np.arange(2 * T + 1)[None, :]
        _cache["chien_pow"] = (-(i * j)) % _ORDER
    return _cache["chien_pow"]  # type: ignore[return-value]


def _chien_roots(sigma: list[int]) -> np.ndarray:
    """Positions i in 0..126 with sigma(alpha^-i) == 0 (error locations)."""
    exp, log = gf_tables()
    pow_m = _chien_pow_matrix()
    vals = np.zeros(_ORDER, dtype=np.uint8)
    for j, cj in enumerate(sigma):
        if cj:
            vals ^= exp[(int(log[cj]) + pow_m[:, j]) % _ORDER]
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
        return None  # wrong root count, or a correction in a shortened position
    corrected = word.copy()
    corrected[pos] ^= 1
    if syndromes(corrected).any():
        return None  # BM sigma did not correspond to a binary error pattern
    return corrected, int(lfsr_len)


def decode(word_bits: np.ndarray) -> tuple[np.ndarray, int] | None:
    """Errors-only BM + Chien decode at full strength t=13.

    Returns (corrected 100-bit word, n_errors_corrected) or None when no
    codeword lies within 13 errors of the input. Rejection conditions:
    BM locator degree > 13, Chien root count != locator degree, a located
    error in a shortened position (>= 100), or a failed final syndrome
    re-check.
    """
    w = _as_word(word_bits, N_WORD)
    return _decode_syndromes(w, syndromes(w))


def decode_many(
    words_bits: np.ndarray,
) -> list[tuple[np.ndarray, int] | None]:
    """Apply :func:`decode` to every row without changing row semantics.

    Initial syndromes are evaluated in one vectorized pass.  Berlekamp-
    Massey, Chien search, shortened-position refusal, and the final syndrome
    recheck remain the same scalar routines used by :func:`decode`, so this
    is an execution optimization only.  Results preserve input row order.
    """
    words = _as_words(words_bits, N_WORD)
    syndrome_rows = _syndromes_many_words(words)
    return [
        _decode_syndromes(words[index], syndrome_rows[index])
        for index in range(words.shape[0])
    ]


def decode_erasures(word_bits: np.ndarray,
                    erasure_idx: np.ndarray) -> tuple[np.ndarray, int] | None:
    """Errors-AND-erasures decode via the binary two-trial fill.

    erasure_idx: positions (0..99) whose input values are UNRELIABLE and
    ignored. Corrects e channel errors outside the erasure set plus
    f = len(erasure_idx) erasures whenever 2e + f <= 26 (= d-1). Method:
    for a BINARY code, filling all erasures with 0 and with 1 gives two
    trials, one of which sees <= e + f/2 errors — within the errors-only
    decoder's reach exactly when the budget holds. Acceptance is gated by
    2*e_out + f <= 26, which makes an accepted decode unique: two distinct
    accepted codewords would lie within (26 - f) + f = 26 < d of each
    other. The budget is ENFORCED HERE and cannot be relaxed by callers
    (e022 v2.1 bug class). Beyond-budget inputs may return None or
    (rarely) a miscorrection, exactly like errors-only decoding beyond t —
    downstream message gates stay the backstop.

    Returns (corrected 100-bit word, e_out) with e_out = corrections at
    NON-erased positions (fill corrections are not channel errors), or
    None. Known-position decoding only: hypothesis SEARCH must not use
    erasures until the Stage-A false-accept budget is re-derived for
    reduced-support words (HOLO-DESIGN §12, carried from PILOTS-DESIGN §14).
    """
    w = _as_word(word_bits, N_WORD)
    era = np.unique(np.asarray(erasure_idx, dtype=np.int64))
    if era.size and (era[0] < 0 or era[-1] >= N_WORD):
        raise ValueError("erasure indices out of range")
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

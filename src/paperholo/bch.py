"""Shortened binary BCH codes over GF(2^7) — pilot window codes (two frozen instances).

layout_version 2 (frozen by the M1 pilot contract): BCH(127,64,t=10) shortened
by 27 -> (100,37), roots alpha^1..alpha^20, designed distance 21.
DECLARED DEVIATION from docs/PILOTS-DESIGN.md v0.1 §6.2: the spec'd
"(127,36,t=15) shortened to (100,36)" is arithmetically impossible (shortening
reduces k, and (100,36,d31) exceeds best-known bounds).

layout_version 3 (frozen by the v3 migration contract): BCH(127,50,t=13)
shortened by 27 -> (100,23), roots alpha^1..alpha^26 (11 cyclotomic cosets:
C1,C3,C5,C7,C9,C11,C13,C15,C19,C21,C23 — C17==C9 and C25==C19 fold in),
generator degree 77, designed distance 27. Message thrift (18-bit flat counter
+ 5 zero pads, no version/plane fields) buys the extra distance; format/plane
identity is implicit in the labeled value scramblers (pilots.py).

Both codes share the field: GF(2^7), primitive polynomial 0x89 = x^7 + x^3 + 1.

Conventions (identical for both instances):
- A word is a uint8 bit array; index i = coefficient of x^i of the code
  polynomial. Full codewords have degree <= 126; the 27 SHORTENED positions
  are the highest-order information positions x^100..x^126, fixed 0 and never
  transmitted. Transmitted (shortened) words are the 100 coefficients x^0..x^99.
- Systematic: message bit j sits at position n_parity + j; positions
  0..n_parity-1 carry the parity remainder (n_parity = 63 for v2, 77 for v3).
- decode() rejects (returns None) when the BM error-locator degree exceeds
  max_errors, when Chien search finds fewer distinct roots than that degree,
  when any located error falls in a shortened position (>= 100), or when the
  corrected word fails the final syndrome re-check.

The module-level function API (encode/decode/syndromes/syndromes_many/
decode_many/generator_poly/message_from_word + the v2 constants) is the FROZEN
layout_version-2 surface — byte-identical behavior, pinned by
tests/test_format_v2_golden.py. The v3 instance lives behind CODE_V3 /
code_for_version(3).

Self-contained: numpy + stdlib only.
"""
from __future__ import annotations

import numpy as np

GF_PRIM_POLY: int = 0x89          # format-axis, frozen (x^7 + x^3 + 1)
N_FULL, K_FULL, T_FULL = 127, 64, 10          # layout_version-2 code
SHORTEN_BY, N_SHORT, K_SHORT = 27, 100, 37
K_FULL_V3, T_FULL_V3, K_SHORT_V3 = 50, 13, 23  # layout_version-3 code

_M = 7
_ORDER = (1 << _M) - 1            # 127, multiplicative order of GF(2^7)*
_N_PARITY = N_FULL - K_FULL       # 63 = deg g(x) for the v2 code

_cache: dict[str, object] = {}


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


def _berlekamp_massey(synd: list[int]) -> tuple[list[int], int]:
    """BM over GF(2^7); returns (sigma coeffs ascending trimmed, L).
    t-independent: works on any syndrome list (length 2t)."""
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


class BCHCode:
    """One narrow-sense shortened binary BCH code over GF(2^7).

    Parameterized by (k_full, t_full); n_full = 127 and shorten_by = 27 are
    shared format constants (both frozen instances transmit 100 bits).
    Instances are immutable in intent — do not mutate after construction.
    """

    def __init__(self, k_full: int, t_full: int) -> None:
        self.n_full = N_FULL
        self.k_full = int(k_full)
        self.t_full = int(t_full)
        self.shorten_by = SHORTEN_BY
        self.n_short = N_SHORT
        self.k_short = self.k_full - SHORTEN_BY
        self.n_parity = N_FULL - self.k_full
        self._c: dict[str, object] = {}
        g = self.generator_poly()          # eager build: asserts deg == n_parity
        assert int(g[self.n_parity]) == 1 and int(g[0]) == 1

    # -- generator ------------------------------------------------------------

    def _cyclotomic_root_set(self) -> set[int]:
        """Union of the 2-cyclotomic cosets mod 127 containing 1..2t."""
        roots: set[int] = set()
        for r in range(1, 2 * self.t_full + 1):
            c = r
            while c not in roots:
                roots.add(c)
                c = (2 * c) % _ORDER
        return roots

    def generator_poly(self) -> np.ndarray:
        """g(x) coefficients ascending (index = power of x), (n_parity+1,)
        uint8, degree n_parity."""
        if "gpoly" not in self._c:
            exp_l, log_l = _tables_list()
            g = [1]  # coefficients in GF(2^7) (they collapse to {0,1} at the end)
            for r in sorted(self._cyclotomic_root_set()):
                ar = exp_l[r % _ORDER]
                # g(x) *= (x + alpha^r)
                new = [0] * (len(g) + 1)
                for i, gi in enumerate(g):
                    if gi:
                        new[i + 1] ^= gi
                        new[i] ^= exp_l[(log_l[gi] + log_l[ar]) % _ORDER]
                g = new
            assert len(g) - 1 == self.n_parity, \
                f"deg g = {len(g) - 1}, expected {self.n_parity}"
            assert all(c in (0, 1) for c in g), "g(x) must be binary"
            self._c["gpoly"] = np.asarray(g, dtype=np.uint8)
            self._c["gpoly_int"] = sum(c << i for i, c in enumerate(g))
        return self._c["gpoly"].copy()  # type: ignore[union-attr]

    def _gpoly_int(self) -> int:
        if "gpoly_int" not in self._c:
            self.generator_poly()
        return self._c["gpoly_int"]  # type: ignore[return-value]

    # -- encode ---------------------------------------------------------------

    def encode(self, message_bits: np.ndarray) -> np.ndarray:
        """Systematic encode: (k_short,) message bits -> (100,) shortened
        codeword."""
        m = _as_word(message_bits, self.k_short)
        m_int = 0
        for j in range(self.k_short):
            if m[j]:
                m_int |= 1 << j
        parity = _polymod2(m_int << self.n_parity, self._gpoly_int())
        word = np.zeros(self.n_short, dtype=np.uint8)
        for i in range(self.n_parity):
            word[i] = (parity >> i) & 1
        word[self.n_parity:] = m
        return word

    def message_from_word(self, word_bits: np.ndarray) -> np.ndarray:
        """(100,) shortened codeword -> (k_short,) systematic message bits."""
        w = _as_word(word_bits, self.n_short)
        return w[self.n_parity:].copy()

    # -- syndromes ------------------------------------------------------------

    def _synd_matrix(self) -> np.ndarray:
        """A[j-1, i] = alpha^(j*i), j in 1..2t, i in 0..99. (2t, 100) uint8."""
        if "synd_matrix" not in self._c:
            exp, _ = gf_tables()
            j = np.arange(1, 2 * self.t_full + 1)[:, None]
            i = np.arange(self.n_short)[None, :]
            self._c["synd_matrix"] = exp[(j * i) % _ORDER]
        return self._c["synd_matrix"]  # type: ignore[return-value]

    def syndromes(self, word_bits: np.ndarray) -> np.ndarray:
        """S_j = w(alpha^j) for j = 1..2t -> (2t,) uint8 GF elements."""
        w = _as_word(word_bits, self.n_short)
        idx = np.flatnonzero(w)
        if idx.size == 0:
            return np.zeros(2 * self.t_full, dtype=np.uint8)
        return np.bitwise_xor.reduce(self._synd_matrix()[:, idx], axis=1)

    def syndromes_many(self, words_bits: np.ndarray) -> np.ndarray:
        """(H, 100) -> (H, 2t) vectorized syndromes (uint8 GF elements)."""
        ws = np.asarray(words_bits, dtype=np.uint8)
        if ws.ndim != 2 or ws.shape[1] != self.n_short:
            raise ValueError(f"expected (H, {self.n_short}), got {ws.shape}")
        a = self._synd_matrix()  # (2t, 100)
        out = np.empty((ws.shape[0], 2 * self.t_full), dtype=np.uint8)
        chunk_rows = 4096
        for lo in range(0, ws.shape[0], chunk_rows):
            blk = ws[lo : lo + chunk_rows]
            prod = blk[:, None, :] * a[None, :, :]  # uint8, elements < 128
            out[lo : lo + chunk_rows] = np.bitwise_xor.reduce(prod, axis=2)
        return out

    # -- decode ---------------------------------------------------------------

    def _chien_pow_matrix(self) -> np.ndarray:
        """P[i, j] = (-i*j) mod 127 for i in 0..126, j in 0..2t. int64."""
        if "chien_pow" not in self._c:
            i = np.arange(_ORDER)[:, None]
            j = np.arange(2 * self.t_full + 1)[None, :]
            self._c["chien_pow"] = (-(i * j)) % _ORDER
        return self._c["chien_pow"]  # type: ignore[return-value]

    def _chien_roots(self, sigma: list[int]) -> np.ndarray:
        """Positions i in 0..126 with sigma(alpha^-i) == 0 (error locations)."""
        exp, log = gf_tables()
        pow_m = self._chien_pow_matrix()
        vals = np.zeros(_ORDER, dtype=np.uint8)
        for j, cj in enumerate(sigma):
            if cj:
                vals ^= exp[(int(log[cj]) + pow_m[:, j]) % _ORDER]
        return np.flatnonzero(vals == 0)

    def _decode_syndromes(
        self, word: np.ndarray, synd: np.ndarray, max_errors: int
    ) -> tuple[np.ndarray, int] | None:
        if not synd.any():
            return word.copy(), 0
        sigma, lfsr_len = _berlekamp_massey([int(s) for s in synd])
        if lfsr_len > max_errors or len(sigma) - 1 != lfsr_len:
            return None
        pos = self._chien_roots(sigma)
        if pos.size != lfsr_len or bool((pos >= self.n_short).any()):
            return None  # wrong root count, or a correction in a shortened position
        corrected = word.copy()
        corrected[pos] ^= 1
        if self.syndromes(corrected).any():
            return None  # BM sigma did not correspond to a binary error pattern
        return corrected, int(lfsr_len)

    def decode(self, word_bits: np.ndarray, max_errors: int
               ) -> tuple[np.ndarray, int] | None:
        """BM + Chien on the shortened code.

        Returns (corrected 100-bit word, n_errors_corrected) or None if no
        codeword lies within max_errors of the input (see module docstring for
        the exact rejection conditions)."""
        if not 0 <= max_errors <= self.t_full:
            raise ValueError(
                f"max_errors must be in 0..{self.t_full}, got {max_errors}")
        w = _as_word(word_bits, self.n_short)
        return self._decode_syndromes(w, self.syndromes(w), max_errors)

    def decode_erasures(self, word_bits: np.ndarray, erasure_idx: np.ndarray,
                        max_errors: int | None = None
                        ) -> tuple[np.ndarray, int] | None:
        """Errors-AND-erasures decode via the binary two-trial fill.

        erasure_idx: positions (0..n_short-1) whose input values are
        UNRELIABLE and ignored. The code corrects e channel errors outside
        the erasure set plus f = len(erasure_idx) erasures whenever
        2e + f <= 2*max_errors (= d-1 at full strength). Method: for a
        BINARY code, filling all erasures with 0 and with 1 gives two
        trials, one of which sees <= e + f/2 errors — within the errors-only
        decoder's reach exactly when the budget holds. Acceptance is gated
        by 2*e_out + f <= 2*max_errors, which makes an accepted decode
        unique: two distinct accepted codewords would lie within
        (26 - f) + f = 26 < d of each other. Beyond-budget inputs may
        return None or (rarely) a miscorrection, exactly like errors-only
        decoding beyond t — downstream message gates stay the backstop.

        Returns (corrected 100-bit word, e_out) with e_out = corrections at
        NON-erased positions (fill corrections are not channel errors), or
        None. Stage-A hypothesis SEARCH must not use erasures until the
        §6.4 false-accept budget is re-derived for reduced-support words
        (PILOTS-DESIGN §14); known-position decoding is safe.
        """
        if max_errors is None:
            max_errors = self.t_full
        if not 0 <= max_errors <= self.t_full:
            raise ValueError(
                f"max_errors must be in 0..{self.t_full}, got {max_errors}")
        w = _as_word(word_bits, self.n_short)
        era = np.unique(np.asarray(erasure_idx, dtype=np.int64))
        if era.size and (era[0] < 0 or era[-1] >= self.n_short):
            raise ValueError("erasure indices out of range")
        f = int(era.size)
        if f > 2 * max_errors:
            return None
        if f == 0:
            res = self.decode(w, max_errors)
            return None if res is None else (res[0], int(res[1]))
        keep = np.ones(self.n_short, dtype=bool)
        keep[era] = False
        best: tuple[np.ndarray, int] | None = None
        for fill in (0, 1):
            trial = w.copy()
            trial[era] = fill
            res = self._decode_syndromes(trial, self.syndromes(trial),
                                         max_errors)
            if res is None:
                continue
            corrected, _ = res
            e_out = int(np.sum(corrected[keep] != w[keep]))
            if 2 * e_out + f > 2 * max_errors:
                continue
            if best is None or e_out < best[1]:
                best = (corrected, e_out)
        return best

    def decode_many(self, words_bits: np.ndarray, max_errors: int
                    ) -> list[tuple[np.ndarray, int] | None]:
        """decode() across hypotheses: vectorized syndrome screen, per-word BM."""
        if not 0 <= max_errors <= self.t_full:
            raise ValueError(
                f"max_errors must be in 0..{self.t_full}, got {max_errors}")
        ws = np.asarray(words_bits, dtype=np.uint8)
        synd_all = self.syndromes_many(ws)
        return [
            self._decode_syndromes(ws[h], synd_all[h], max_errors)
            for h in range(ws.shape[0])
        ]


# --- frozen instances (asserted at import: format-axis generator degrees) ----

CODE_V2 = BCHCode(K_FULL, T_FULL)              # (100,37), t=10, deg g = 63
CODE_V3 = BCHCode(K_FULL_V3, T_FULL_V3)        # (100,23), t=13, deg g = 77
assert CODE_V2.n_parity == 63 and CODE_V2.k_short == K_SHORT
assert CODE_V3.n_parity == 77 and CODE_V3.k_full == 50 \
    and CODE_V3.k_short == K_SHORT_V3


def code_for_version(layout_version: int) -> BCHCode:
    """The pilot window code frozen for a layout_version (2, 3 or 4 —
    v4 reuses the v3 code verbatim: only the value scramble label
    changes, PILOTS-DESIGN §16.1)."""
    if layout_version == 2:
        return CODE_V2
    if layout_version in (3, 4):
        return CODE_V3
    raise ValueError(f"no BCH code defined for layout_version {layout_version}")


# --- frozen layout_version-2 module-level API (byte-identical delegation) ----

def generator_poly() -> np.ndarray:
    """g(x) coefficients ascending (index = power of x), (64,) uint8, deg 63."""
    return CODE_V2.generator_poly()


def encode(message_bits: np.ndarray) -> np.ndarray:
    """Systematic encode: (37,) message bits -> (100,) shortened codeword."""
    return CODE_V2.encode(message_bits)


def message_from_word(word_bits: np.ndarray) -> np.ndarray:
    """(100,) shortened codeword -> (37,) systematic message bits."""
    return CODE_V2.message_from_word(word_bits)


def syndromes(word_bits: np.ndarray) -> np.ndarray:
    """S_j = w(alpha^j) for j = 1..20 -> (20,) uint8 GF elements."""
    return CODE_V2.syndromes(word_bits)


def syndromes_many(words_bits: np.ndarray) -> np.ndarray:
    """(H, 100) -> (H, 20) vectorized syndromes (uint8 GF elements)."""
    return CODE_V2.syndromes_many(words_bits)


def decode(word_bits: np.ndarray, max_errors: int) -> tuple[np.ndarray, int] | None:
    """BM + Chien on the shortened v2 code (see BCHCode.decode)."""
    return CODE_V2.decode(word_bits, max_errors)


def decode_many(
    words_bits: np.ndarray, max_errors: int
) -> list[tuple[np.ndarray, int] | None]:
    """decode() across hypotheses: vectorized syndrome screen, per-word BM."""
    return CODE_V2.decode_many(words_bits, max_errors)

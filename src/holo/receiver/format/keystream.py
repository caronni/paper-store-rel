from __future__ import annotations

import hashlib

import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, CipherContext, algorithms, modes
from numpy.typing import ArrayLike

#: Frozen domain bytes: the (aux, major, u, v) meaning of each number
#: is printed format, not a local convention.  NEVER RENUMBER — only
#: append.  The table with each domain's address fields is
#: conversion_docs/03-keystream-metadata.md:69.
DOMAIN_PAYLOAD = 1
DOMAIN_PILOT_VALUES = 2
DOMAIN_FILLER_VALUES = 3
DOMAIN_PILOT_SITES = 4
DOMAIN_FILLER_SITES = 5
DOMAIN_SLOT_PERM = 6
DOMAIN_FOUNTAIN_ROW = 7
DOMAIN_BLOCK_ASSIGN = 8
DOMAIN_COLOR_DUST_ORDER = 9
DOMAIN_CMY7_INTERLEAVE = 10
DOMAIN_CMY7_DITHER = 11
DOMAIN_COLOR_CELL_ORDER = 12
DOMAIN_CMY8_DITHER = 13
DOMAIN_COLOR_FOUNTAIN_ROW = 14
DOMAIN_COLOR_BLOCK_ASSIGN = 15
#: `'CMYK'.index('K')` — the v1 plane convention (C=0 M=1 Y=2 K=3).
#: It is the keystream aux of domains 1/2/3, not a stream index: a
#: cmy8 row's C stream has plane 0.
PLANE_K = 3

#: Frozen colour-stream auxiliaries.  CMY7 is single-stream but rides
#: domains 14/15 at aux 0 ("main"), NOT K's domains 7/8: routing it
#: through K's domains is a silent fork that still "decodes", to
#: garbage (conversion_docs/05-fountain.md:49).
COLOR_STREAM_MAIN = 0
COLOR_STREAM_C = 1
COLOR_STREAM_M = 2
COLOR_STREAM_Y = 3
COLOR_STREAM_AUX: dict[str, int] = {
    "main": COLOR_STREAM_MAIN,
    "C": COLOR_STREAM_C,
    "M": COLOR_STREAM_M,
    "Y": COLOR_STREAM_Y,
}

#: The KDF label, `b"holo/v1|"` for BOTH namespaces: a v2 identity
#: lives in the SEED payload, never in this prefix.  Changing it
#: re-keys every printed sheet
#: (conversion_docs/04-format-identity.md:63-64).
_KDF_PREFIX = b"holo/v1|"
#: pilots.N_WORD_SITES, restated: domain 9's cmy word keys follow the
#: tile's dust keys, one per word site.
_WORD_SITES = 100
#: 1,048,576 counters = 16 MiB per AES call.  This chunking is what
#: keeps a full-page keystream regeneration inside the memory budget:
#: peak is chunk + output, never an intermediate full-size grid
#: (conversion_docs/03-keystream-metadata.md:57-60, :366-367).
_CHUNK_BLOCKS = 1 << 20


def kdf(seed: bytes) -> bytes:
    return hashlib.sha256(_KDF_PREFIX + seed).digest()[:16]


#: These range checks and the retry>64 caps below are the two guards
#: the charter's C-7 answer deliberately KEPT: an out-of-range field
#: does not fail, it wraps into a valid DIFFERENT stream, which no
#: downstream gate can see (conversion_docs/03-keystream-metadata.md:371).
def counters(domain: int, aux: int, major: ArrayLike, u: ArrayLike,
             v: ArrayLike) -> np.ndarray:
    major = np.asarray(major, dtype=np.int64)
    u = np.asarray(u, dtype=np.int64)
    v = np.asarray(v, dtype=np.int64)
    major, u, v = np.broadcast_arrays(major, u, v)
    if not (0 <= domain <= 0xFF and 0 <= aux <= 0xFF):
        raise ValueError("domain/aux out of range")
    for name, arr, hi in (("major", major, 1 << 24),
                          ("u", u, 1 << 32), ("v", v, 1 << 32)):
        if arr.size and (int(arr.min()) < 0 or int(arr.max()) >= hi):
            raise ValueError(f"counter field {name} out of range")
    n = major.size
    ctr = np.zeros((n, 16), dtype=np.uint8)
    ctr[:, 0] = domain
    ctr[:, 1] = aux
    fm = major.ravel()
    fu = u.ravel()
    fv = v.ravel()
    ctr[:, 2] = (fm >> 16) & 0xFF
    ctr[:, 3] = (fm >> 8) & 0xFF
    ctr[:, 4] = fm & 0xFF
    for col, arr in ((5, fu), (9, fv)):
        ctr[:, col] = (arr >> 24) & 0xFF
        ctr[:, col + 1] = (arr >> 16) & 0xFF
        ctr[:, col + 2] = (arr >> 8) & 0xFF
        ctr[:, col + 3] = arr & 0xFF
    return ctr


def _encryptor(seed: bytes) -> CipherContext:
    return Cipher(algorithms.AES(kdf(seed)), modes.ECB()).encryptor()


def blocks(seed: bytes, domain: int, aux: int, major: ArrayLike,
           u: ArrayLike, v: ArrayLike) -> np.ndarray:
    major = np.asarray(major, dtype=np.int64)
    u = np.asarray(u, dtype=np.int64)
    v = np.asarray(v, dtype=np.int64)
    major, u, v = np.broadcast_arrays(major, u, v)
    fm, fu, fv = major.ravel(), u.ravel(), v.ravel()
    enc = _encryptor(seed)
    out = np.empty((fm.size, 16), dtype=np.uint8)
    for lo in range(0, fm.size, _CHUNK_BLOCKS):
        hi = min(lo + _CHUNK_BLOCKS, fm.size)
        ctr = counters(domain, aux, fm[lo:hi], fu[lo:hi], fv[lo:hi])
        out[lo:hi] = np.frombuffer(enc.update(ctr.tobytes()),
                                   dtype=np.uint8).reshape(-1, 16)
    return out


def bits(seed: bytes, domain: int, aux: int, major: ArrayLike,
         u: ArrayLike, v: ArrayLike) -> np.ndarray:
    major = np.asarray(major, dtype=np.int64)
    u = np.asarray(u, dtype=np.int64)
    v = np.asarray(v, dtype=np.int64)
    major, u, v = np.broadcast_arrays(major, u, v)
    fm, fu, fv = major.ravel(), u.ravel(), v.ravel()
    enc = _encryptor(seed)
    out = np.empty(fm.size, dtype=np.uint8)
    for lo in range(0, fm.size, _CHUNK_BLOCKS):
        hi = min(lo + _CHUNK_BLOCKS, fm.size)
        ctr = counters(domain, aux, fm[lo:hi], fu[lo:hi], fv[lo:hi])
        enc_bytes = np.frombuffer(enc.update(ctr.tobytes()), dtype=np.uint8)
        out[lo:hi] = enc_bytes[0::16] >> 7
    return out


def keys64(seed: bytes, domain: int, aux: int, major: ArrayLike,
           u: ArrayLike, v: ArrayLike) -> np.ndarray:
    blk = blocks(seed, domain, aux, major, u, v)
    return blk[:, :8].astype(np.uint64) @ (1 << (8 * np.arange(
        7, -1, -1, dtype=np.uint64)))


#: Scramble addresses are ABSOLUTE page-cell coordinates (the e016
#: align_to_field bug class): a tile-local spelling decodes tile (0,0)
#: and nothing else (conversion_docs/03-keystream-metadata.md:343-345,
#: experiments/016-arch3-c2-volume.md).
def payload_bits(seed: bytes, plane: int, page: int,
                 cells_yx: tuple[int, int]) -> np.ndarray:
    h, w = cells_yx
    out = np.empty((h, w), dtype=np.uint8)
    rows_per = max(1, _CHUNK_BLOCKS // max(w, 1))
    x = np.arange(w, dtype=np.int64)
    for y0 in range(0, h, rows_per):
        y1 = min(y0 + rows_per, h)
        yy = np.repeat(np.arange(y0, y1, dtype=np.int64), w)
        xx = np.tile(x, y1 - y0)
        out[y0:y1] = bits(seed, DOMAIN_PAYLOAD, plane, page,
                          yy, xx).reshape(y1 - y0, w)
    return out


def fountain_rows_bits(seed: bytes, block_index: int, rows: ArrayLike,
                       n_cols: int) -> np.ndarray:
    rows = np.asarray(rows, dtype=np.int64).ravel()
    n_words = -(-n_cols // 128)
    rr = np.repeat(rows, n_words)
    ww = np.tile(np.arange(n_words, dtype=np.int64), rows.size)
    blk = blocks(seed, DOMAIN_FOUNTAIN_ROW, 0, block_index, rr, ww)
    bits_all = np.unpackbits(blk.reshape(rows.size, n_words * 16),
                             axis=1, bitorder="big")
    return bits_all[:, :n_cols]


#: The ordinal tie-break in the lexsort is format law, not tidiness:
#: it makes a 64-bit key collision fully specified instead of
#: dependent on a sort implementation
#: (conversion_docs/03-keystream-metadata.md:124-127).
def _item_permutation(seed: bytes, domain: int, tile_counter: int,
                      size: int) -> np.ndarray:
    index = np.arange(size, dtype=np.int64)
    keys = keys64(seed, domain, 0, tile_counter, index, 0)
    return np.lexsort((index, keys)).astype(np.int64, copy=False)


def color_dust_permutation(seed: bytes, tile_counter: int,
                           size: int = 20) -> np.ndarray:
    return _item_permutation(
        seed, DOMAIN_COLOR_DUST_ORDER, tile_counter, size)


#: cmy's word '0' per word site 0..99: True = Y, False = W.  Domain 9
#: PAST the tile's dust draw: site i reads the key at u = n_dust + i,
#: its MSB chooses Y (CMY-DESIGN §2.5, R10).
def color_word_zero_mask(seed: bytes, tile_counter: int,
                         n_dust: int) -> np.ndarray:
    sites = n_dust + np.arange(_WORD_SITES, dtype=np.int64)
    return bits(seed, DOMAIN_COLOR_DUST_ORDER, 0, tile_counter,
                sites, 0).astype(bool)


def cmy7_interleave_permutation(seed: bytes, tile_counter: int,
                                size: int = 10934) -> np.ndarray:
    return _item_permutation(
        seed, DOMAIN_CMY7_INTERLEAVE, tile_counter, size)


def cmy7_dither_bits(seed: bytes, tile_counter: int,
                     size: int = 10934) -> np.ndarray:
    return bits(
        seed, DOMAIN_CMY7_DITHER, 0, tile_counter,
        np.arange(size, dtype=np.int64), 0)


def color_cell_permutation(seed: bytes, tile_counter: int,
                           size: int = 3976) -> np.ndarray:
    return _item_permutation(
        seed, DOMAIN_COLOR_CELL_ORDER, tile_counter, size)


def _color_stream_aux(stream: str | int) -> int:
    if isinstance(stream, str):
        return COLOR_STREAM_AUX[stream]
    return stream


def cmy8_dither_bits(seed: bytes, stream: str | int, tile_counter: int,
                     size: int = 3976) -> np.ndarray:
    aux = _color_stream_aux(stream)
    return bits(
        seed, DOMAIN_CMY8_DITHER, aux, tile_counter,
        np.arange(size, dtype=np.int64), 0)


def color_fountain_rows_bits(seed: bytes, stream: str | int,
                             block_index: int, rows: ArrayLike,
                             n_cols: int) -> np.ndarray:
    aux = _color_stream_aux(stream)
    rows = np.asarray(rows, dtype=np.int64).ravel()
    n_words = -(-n_cols // 128)
    rr = np.repeat(rows, n_words)
    ww = np.tile(np.arange(n_words, dtype=np.int64), rows.size)
    blk = blocks(
        seed, DOMAIN_COLOR_FOUNTAIN_ROW, aux, block_index, rr, ww)
    bits_all = np.unpackbits(
        blk.reshape(rows.size, n_words * 16), axis=1, bitorder="big")
    return bits_all[:, :n_cols]


def color_block_assign_keys(seed: bytes, stream: str | int, page: int,
                            local_tiles: ArrayLike) -> np.ndarray:
    aux = _color_stream_aux(stream)
    local_tiles = np.asarray(local_tiles, dtype=np.int64)
    return keys64(
        seed, DOMAIN_COLOR_BLOCK_ASSIGN, aux, page, local_tiles, 0)


def bounded_draws(seed: bytes, domain: int, u: ArrayLike,
                  bound: int) -> np.ndarray:
    u = np.asarray(u, dtype=np.int64).ravel()
    limit = 256 - (256 % bound)
    out = np.full(u.size, -1, dtype=np.int64)
    pend = np.arange(u.size)
    retry = 0
    while pend.size:
        blk = blocks(seed, domain, 0, 0, u[pend], retry)
        done = np.zeros(pend.size, dtype=bool)
        for byte in range(16):
            b = blk[:, byte].astype(np.int64)
            take = (~done) & (b < limit)
            out[pend[take]] = b[take] % bound
            done |= take
        pend = pend[~done]
        retry += 1
        if retry > 64:
            raise RuntimeError("bounded_draws rejection runaway")
    return out


#: `a_t` = the first admissible VALUE (w % n_slots) coprime to n_slots
#: (bijectivity); `b_t` = the NEXT one.  The `~take_a` term is format
#: law: a scalar rewrite that lets one word serve both forks every
#: tile's permutation (conversion_docs/03-keystream-metadata.md:346-348).
def slot_perm_params(seed: bytes, tile_counter: ArrayLike, n_slots: int
                     ) -> tuple[np.ndarray, np.ndarray]:
    tc = np.asarray(tile_counter, dtype=np.int64).ravel()
    limit = 65536 - (65536 % n_slots)
    a = np.zeros(tc.size, dtype=np.int64)
    b = np.zeros(tc.size, dtype=np.int64)
    have_a = np.zeros(tc.size, dtype=bool)
    have_b = np.zeros(tc.size, dtype=bool)
    pend = np.arange(tc.size)
    retry = 0
    while pend.size:
        blk = blocks(seed, DOMAIN_SLOT_PERM, 0, 0, tc[pend], retry)
        words = (blk[:, 0:16:2].astype(np.int64) << 8) | \
            blk[:, 1:16:2].astype(np.int64)
        for wi in range(8):
            w = words[:, wi]
            ok = w < limit
            val = w % n_slots
            coprime = np.gcd(val, n_slots) == 1
            take_a = ok & coprime & ~have_a[pend]
            a[pend[take_a]] = val[take_a]
            have_a[pend] |= take_a
            take_b = ok & have_a[pend] & ~have_b[pend] & ~take_a
            b[pend[take_b]] = val[take_b]
            have_b[pend] |= take_b
        pend = pend[~(have_a[pend] & have_b[pend])]
        retry += 1
        if retry > 64:
            raise RuntimeError("slot_perm_params rejection runaway")
    return a, b

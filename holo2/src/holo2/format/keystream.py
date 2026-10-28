"""Printed-format-v1 keystream: AES-128 as a pure function of address.

CARRIED VERBATIM (holo2 firewall: copy-and-adapt, never import) from
``src/holo/core/keystream.py``, restricted to the draw forms the fountain
close needs.  The format is unchanged and this arithmetic is FORMAT-AXIS
(HOLO-DESIGN §5): every value below must stay bit-identical to the v1
generator or printed sheets stop decoding.

  key             = SHA-256(b"holo/v1|" || seed)[0:16]
  counter(addr)   = 16 bytes, big-endian fields:
                      [0]     domain
                      [1]     aux      (stream index, or 0)
                      [2:5]   major    (24-bit: page, or fountain block)
                      [5:9]   u        (32-bit: local tile / row)
                      [9:13]  v        (32-bit: column word)
                      [13:16] zero
  block(addr)     = AES-128-Encrypt(key, counter(addr))     # FIPS-197

  DOMAINS CARRIED HERE (the close's four, plus the six the K tile decode
  chain needs; the COLOR domains 9-13 arrive with the color leaves, H7):
    1  payload scramble    aux=plane  major=page  u=cell y     v=cell x
    2  pilot word values   aux=plane  major=0     u=site idx   v=0
    3  filler values       aux=plane  major=page  u=cell y     v=cell x
    4  pilot sites         aux=0      major=0     u=quota idx  v=retry
    5  filler sites        aux=0      major=0     u=filler idx v=retry
    6  slot-perm params    aux=0      major=0     u=tile ctr   v=retry
    7  fountain rows       aux=0      major=block u=row        v=col word
    8  block assignment    aux=0      major=page  u=local tile v=0
   14  color fountain row  aux=stream major=block u=row        v=col word
   15  color block assign  aux=stream major=page  u=local tile v=0

  Domains 7/14 pack 128 repair coefficients per AES block: coefficient c
  of (block, row) = bit (c % 128), MSB-first, of the block at
  v = c // 128.  Domains 8/15 draw one 64-bit big-endian sort key from
  block bytes 0..7.  Color stream auxiliaries are frozen: 0=CMY7 main,
  1=CMY8 C, 2=CMY8 M, 3=CMY8 Y.

  Domains 1/2/3 draw one bit per address — the MSB of block byte 0.
  Domain 4/5 draw uniformly in [0, bound) by the spec'd 8-bit rejection
  rule; domain 6 by the 16-bit rejection scan (see the two functions).
  The plane index is 'CMYK'.index(plane), so the K plane = 3.

  ONE BYTE-ORDER DOCTRINE (§13.12): every multi-byte integer field is
  big-endian and every bit string MSB-first, so numpy's default
  packbits/unpackbits bit order is the format's.
"""
from __future__ import annotations

import hashlib
from types import MappingProxyType

import numpy as np
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DOMAIN_PAYLOAD = 1             # aux=plane, major=page, u=cell y, v=cell x
DOMAIN_PILOT_VALUES = 2        # aux=plane, major=0,    u=site index, v=0
DOMAIN_FILLER_VALUES = 3       # aux=plane, major=page, u=cell y, v=cell x
DOMAIN_PILOT_SITES = 4         # aux=0, major=0, u=quota index, v=retry
DOMAIN_FILLER_SITES = 5        # aux=0, major=0, u=quota index, v=retry
DOMAIN_SLOT_PERM = 6           # aux=0, major=0, u=tile counter, v=retry
DOMAIN_FOUNTAIN_ROW = 7        # aux=0, major=block, u=row, v=column word
DOMAIN_BLOCK_ASSIGN = 8        # aux=0, major=page, u=local tile, v=0
DOMAIN_COLOR_FOUNTAIN_ROW = 14
DOMAIN_COLOR_BLOCK_ASSIGN = 15
PLANE_K = 3                    # 'CMYK'.index('K') — the v1 plane convention

COLOR_STREAM_MAIN = 0
COLOR_STREAM_C = 1
COLOR_STREAM_M = 2
COLOR_STREAM_Y = 3
COLOR_STREAM_AUX = MappingProxyType({
    "main": COLOR_STREAM_MAIN,
    "C": COLOR_STREAM_C,
    "M": COLOR_STREAM_M,
    "Y": COLOR_STREAM_Y,
})

_KDF_PREFIX = b"holo/v1|"
_CHUNK_BLOCKS = 1 << 20   # 16 MiB of counters per AES call


def kdf(seed: bytes) -> bytes:
    """Per-seed AES key: SHA-256(b"holo/v1|" || seed)[0:16]."""
    if not isinstance(seed, bytes) or not seed:
        raise ValueError("seed must be non-empty bytes")
    return hashlib.sha256(_KDF_PREFIX + seed).digest()[:16]


def counters(domain: int, aux: int, major, u, v) -> np.ndarray:
    """Structured counter blocks, shape (N, 16) uint8, big-endian fields.

    major/u/v broadcast against each other (numpy rules); domain and aux
    are scalars. Field ranges are enforced — an out-of-range address is a
    format bug, never silently wrapped.
    """
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


def _encryptor(seed: bytes):
    return Cipher(algorithms.AES(kdf(seed)), modes.ECB(),
                  backend=default_backend()).encryptor()


def blocks(seed: bytes, domain: int, aux: int, major, u,
           v) -> np.ndarray:
    """AES blocks for the given addresses, shape (N, 16) uint8.

    ECB over structured counters == CTR with an explicit counter.  The
    default registry seeds are public format constants, so their streams
    provide no confidentiality.  Allocations are chunked: peak memory is
    bounded by the chunk size plus the output.
    """
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


def bits(seed: bytes, domain: int, aux: int, major, u, v) -> np.ndarray:
    """Keystream bits (uint8 0/1), one per address; MSB of block byte 0.

    Streams in chunks: only the output bit array is ever full-size.
    """
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


def keys64(seed: bytes, domain: int, aux: int, major, u,
           v) -> np.ndarray:
    """One 64-bit sort key per address: big-endian uint64 of block
    bytes 0..7 (the DOMAIN_BLOCK_ASSIGN draw form)."""
    blk = blocks(seed, domain, aux, major, u, v)
    return blk[:, :8].astype(np.uint64) @ (1 << (8 * np.arange(
        7, -1, -1, dtype=np.uint64)))


def fountain_rows_bits(seed: bytes, block_index: int, rows,
                       n_cols: int) -> np.ndarray:
    """Repair-row coefficients, shape (len(rows), n_cols) uint8.

    Packed draw form (documented exception, see the domain table):
    coefficient c of a row = bit (c % 128), MSB-first, of the AES block
    at (DOMAIN_FOUNTAIN_ROW, 0, block_index, row, c // 128).
    """
    rows = np.asarray(rows, dtype=np.int64).ravel()
    n_words = -(-n_cols // 128)
    rr = np.repeat(rows, n_words)
    ww = np.tile(np.arange(n_words, dtype=np.int64), rows.size)
    blk = blocks(seed, DOMAIN_FOUNTAIN_ROW, 0, block_index, rr, ww)
    bits_all = np.unpackbits(blk.reshape(rows.size, n_words * 16),
                             axis=1, bitorder="big")
    return bits_all[:, :n_cols]


def color_stream_aux(stream: str | int, *, allow_main: bool = True) -> int:
    """The frozen auxiliary byte of one logical color stream."""
    if isinstance(stream, str):
        try:
            aux = COLOR_STREAM_AUX[stream]
        except KeyError:
            raise ValueError(
                f"unknown color stream {stream!r}; "
                f"known: {tuple(COLOR_STREAM_AUX)}") from None
    elif isinstance(stream, int) and not isinstance(stream, bool):
        aux = stream
    else:
        raise TypeError("color stream must be a stream ID or integer aux")
    lo = COLOR_STREAM_MAIN if allow_main else COLOR_STREAM_C
    if not lo <= aux <= COLOR_STREAM_Y:
        expected = "0..3" if allow_main else "1..3"
        raise ValueError(f"color stream auxiliary must be in {expected}")
    return aux


def color_fountain_rows_bits(seed: bytes, stream: str | int,
                             block_index: int, rows,
                             n_cols: int) -> np.ndarray:
    """Color-stream repair rows, using domain 14's packed draw form."""
    aux = color_stream_aux(stream)
    rows = np.asarray(rows, dtype=np.int64).ravel()
    if not isinstance(n_cols, int) or isinstance(n_cols, bool):
        raise TypeError("n_cols must be an integer")
    if n_cols < 0:
        raise ValueError("n_cols must be >= 0")
    n_words = -(-n_cols // 128)
    rr = np.repeat(rows, n_words)
    ww = np.tile(np.arange(n_words, dtype=np.int64), rows.size)
    blk = blocks(
        seed, DOMAIN_COLOR_FOUNTAIN_ROW, aux, block_index, rr, ww)
    bits_all = np.unpackbits(
        blk.reshape(rows.size, n_words * 16), axis=1, bitorder="big")
    return bits_all[:, :n_cols]


def color_block_assign_keys(seed: bytes, stream: str | int, page: int,
                            local_tiles) -> np.ndarray:
    """Color-stream 64-bit page-assignment keys (domain 15)."""
    aux = color_stream_aux(stream)
    local_tiles = np.asarray(local_tiles, dtype=np.int64)
    return keys64(
        seed, DOMAIN_COLOR_BLOCK_ASSIGN, aux, page, local_tiles, 0)


def bounded_draws(seed: bytes, domain: int, u, bound: int) -> np.ndarray:
    """One uniform draw in [0, bound) per u address, via the spec'd
    rejection rule (scan block bytes 0..15, then v+1). bound <= 256."""
    if not 1 <= bound <= 256:
        raise ValueError("bound must be in 1..256")
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
        if retry > 64:  # p(reject)^(16*64) — unreachable; guards a bug
            raise RuntimeError("bounded_draws rejection runaway")
    return out


def slot_perm_params(seed: bytes, tile_counter, n_slots: int
                     ) -> tuple[np.ndarray, np.ndarray]:
    """Per-tile affine slot-permutation parameters (HOLO-DESIGN §4.4).

    The permutation j -> (a_t*j + b_t) % n_slots runs over the tile's
    TRANSMITTED code positions (n_slots = 4096 - n_sites, not a power of
    two), so both parameters come from the spec'd unbiased 16-bit
    rejection scan: read big-endian words from block bytes (0,1), (2,3),
    ... (14,15), then v+1; a word w is admissible when
    w < 65536 - (65536 % n_slots), giving value w % n_slots. a_t = the
    first admissible value with gcd(value, n_slots) == 1 (bijectivity);
    b_t = the next admissible value, unconditioned.
    """
    if not 2 <= n_slots <= 65536:
        raise ValueError("n_slots out of range")
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
            blk[:, 1:16:2].astype(np.int64)          # (n_pend, 8)
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


__all__ = [
    "COLOR_STREAM_AUX",
    "COLOR_STREAM_C",
    "COLOR_STREAM_M",
    "COLOR_STREAM_MAIN",
    "COLOR_STREAM_Y",
    "DOMAIN_BLOCK_ASSIGN",
    "DOMAIN_COLOR_BLOCK_ASSIGN",
    "DOMAIN_COLOR_FOUNTAIN_ROW",
    "DOMAIN_FILLER_SITES",
    "DOMAIN_FILLER_VALUES",
    "DOMAIN_FOUNTAIN_ROW",
    "DOMAIN_PAYLOAD",
    "DOMAIN_PILOT_SITES",
    "DOMAIN_PILOT_VALUES",
    "DOMAIN_SLOT_PERM",
    "PLANE_K",
    "bits",
    "blocks",
    "bounded_draws",
    "color_block_assign_keys",
    "color_fountain_rows_bits",
    "color_stream_aux",
    "counters",
    "fountain_rows_bits",
    "kdf",
    "keys64",
    "slot_perm_params",
]

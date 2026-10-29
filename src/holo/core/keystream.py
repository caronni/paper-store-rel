"""holo format-v1 keystream: AES-128 as a pure function of address.

FORMAT-AXIS (HOLO-DESIGN §5). Every format-defining bit stream — payload
scramble, pilot word values, filler values, fountain repair rows, site
constructions, slot-permutation parameters — is derived here and nowhere
else. There is no sequential stream, no consumption state, no dtype
semantics: one AES block per drawn value, addressed by a structured
counter. Any fragment regenerates exactly its own slice.

THE COMPLETE SPEC (printable; the pure-Python mirror in keystream_spec.py
is the normative reference-as-code, golden-vector pinned):

  key             = SHA-256(b"holo/v1|" || seed)[0:16]
  counter(addr)   = byte layout, 16 bytes, big-endian fields:
                      [0]     domain
                      [1]     aux      (plane index, or 0)
                      [2:5]   major    (24-bit: page, or fountain block)
                      [5:9]   u        (32-bit: cell y / site index / row)
                      [9:13]  v        (32-bit: cell x / retry / column)
                      [13:16] zero
  block(addr)     = AES-128-Encrypt(key, counter(addr))     # FIPS-197
  bit(addr)       = block(addr)[0] >> 7
  bounded draw    = first byte b of block(addr) with
                    b < 256 - (256 % bound), value b % bound; scan bytes
                    0..15, then retry with v+1 (bound <= 256)

  DOMAIN TABLE (format-frozen values + per-domain address fields; plane
  index convention: 'CMYK'.index(plane), so the K plane = 3):
    1 payload scramble   aux=plane  major=page   u=cell y   v=cell x
    2 pilot word values  aux=plane  major=0      u=site idx v=0
    3 filler values      aux=plane  major=page   u=cell y   v=cell x
    4 pilot sites        aux=0      major=0      u=quota idx v=retry
    5 filler sites       aux=0      major=0      u=filler idx v=retry
    6 slot-perm params   aux=0      major=0      u=tile ctr  v=retry
    7 fountain rows      aux=0      major=block  u=row       v=col word
                         (packed: 128 coefficients per block, MSB-first)
    8 block assignment   aux=0      major=page   u=local tile v=0
                         (one 64-bit big-endian sort key, bytes 0..7)
    9 color dust order   aux=0      major=tile   u=base ordinal v=0
                         (one 64-bit big-endian sort key, bytes 0..7;
                         cmy word '0' sites at u = n_dust + site,
                         Y iff the key's MSB)
   10 CMY7 interleave    aux=0      major=tile   u=code-bit idx v=0
                         (one 64-bit big-endian sort key, bytes 0..7)
   11 CMY7 dither        aux=0      major=tile   u=wire-bit idx v=0
   12 color cell order   aux=0      major=tile   u=state ordinal v=0
                         (one 64-bit big-endian sort key, bytes 0..7)
   13 CMY8 dither        aux=stream major=tile   u=cell ordinal v=0
   14 color fountain row aux=stream major=block  u=row v=column word
                         (packed exactly like domain 7)
   15 color block assign aux=stream major=page   u=local tile v=0
                         (one 64-bit big-endian sort key, bytes 0..7)

  Color stream auxiliaries are also frozen: 0=CMY7 main, 1=CMY8 C,
  2=CMY8 M, 3=CMY8 Y.  The row seed already separates CMY7 from CMY8
  and c2 from c3; the auxiliary separates sibling logical streams.

  ONE BYTE-ORDER DOCTRINE (format-wide, §13.12): every multi-byte
  integer field is big-endian, and every bit string is MSB-first —
  bit j of a byte sequence is (byte[j // 8] >> (7 - j % 8)) & 1, so
  bit(addr) is the MSB of block byte 0 and numpy's default packbits/
  unpackbits bitorder is the format's. No LSB-first form exists
  anywhere on the format surface.

Seeds are the format registry's default public constants (HOLO-DESIGN
§4.5): row seeds carry the page geometry (wrong-geometry hypotheses
descramble to coin flips and refuse at the word gate); family seeds key
the geometry-free site constructions so lattice acquisition is shared
across rows. Domain separation lives in the counter's domain byte under
one key per seed — there is no separate label layer.

LLR/GT discipline: ground truth flows through this module or
render-extraction, never retyped draws (012.3 incident rule, carried).
"""
from __future__ import annotations

import hashlib
from types import MappingProxyType

import numpy as np
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# ---------------------------------------------------------------- domains
# One byte each; per-domain (aux, major, u, v) meanings are part of the
# printed format. Never renumber — add.
DOMAIN_PAYLOAD = 1        # aux=plane, major=page, u=cell y, v=cell x
DOMAIN_PILOT_VALUES = 2   # aux=plane, major=0,    u=site index, v=0
DOMAIN_FILLER_VALUES = 3  # aux=plane, major=page, u=cell y, v=cell x
DOMAIN_PILOT_SITES = 4    # aux=0, major=0, u=quota index, v=retry
DOMAIN_FILLER_SITES = 5   # aux=0, major=0, u=quota index, v=retry
DOMAIN_SLOT_PERM = 6      # aux=0, major=0, u=tile counter, v=retry
DOMAIN_FOUNTAIN_ROW = 7   # aux=0, major=block, u=row, v=column word
DOMAIN_BLOCK_ASSIGN = 8   # aux=0, major=page, u=local tile index, v=0
DOMAIN_COLOR_DUST_ORDER = 9
DOMAIN_CMY7_INTERLEAVE = 10
DOMAIN_CMY7_DITHER = 11
DOMAIN_COLOR_CELL_ORDER = 12
DOMAIN_CMY8_DITHER = 13
DOMAIN_COLOR_FOUNTAIN_ROW = 14
DOMAIN_COLOR_BLOCK_ASSIGN = 15
PLANE_K = 3               # 'CMYK'.index('K') — the v1 plane convention

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

# Two documented exceptions to one-block-per-drawn-value (bulk domains):
#   DOMAIN_FOUNTAIN_ROW and DOMAIN_COLOR_FOUNTAIN_ROW pack 128 repair
#   coefficients per AES block:
#     coefficient c of (block, row) = bit (c % 128) of the block at
#     v = c // 128, where bit j of a 16-byte block is
#     (byte[j // 8] >> (7 - j % 8)) & 1  (MSB-first, the format-wide bit
#     order; consistent with bit(addr) = block[0] >> 7 being bit 0).
#   Key/permutation domains draw one 64-bit sort key per item: big-endian
#     uint64 from block bytes 0..7.

_KDF_PREFIX = b"holo/v1|"
_CHUNK_BLOCKS = 1 << 20   # 16 MiB of counters per AES call
_WORD_SITES = 100


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


def blocks(seed: bytes, domain: int, aux: int, major, u, v) -> np.ndarray:
    """AES blocks for the given addresses, shape (N, 16) uint8.

    ECB over structured counters == CTR with an explicit counter; the
    The default registry seeds are public format constants, so their streams
    provide no confidentiality.  A secret seed would make this a keyed PRF,
    but format v1 does not yet define the nonce, authentication, key identity,
    or secret-storage contract required for a supported encryption mode;
    reusing one secret at the same addresses would reuse the stream.
    Allocations are chunked: peak memory is bounded by the chunk size
    plus the output, never by intermediate full-size grids.
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


def keys64(seed: bytes, domain: int, aux: int, major, u, v) -> np.ndarray:
    """One 64-bit sort key per address: big-endian uint64 of block
    bytes 0..7 (the DOMAIN_BLOCK_ASSIGN draw form)."""
    blk = blocks(seed, domain, aux, major, u, v)
    return blk[:, :8].astype(np.uint64) @ (1 << (8 * np.arange(
        7, -1, -1, dtype=np.uint64)))


def payload_bits(seed: bytes, plane: int, page: int,
                 cells_yx: tuple[int, int]) -> np.ndarray:
    """The page's payload scramble field, shape cells_yx, uint8 0/1.

    Generated row-stripe by row-stripe; no full-page coordinate grids.
    """
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


def _item_permutation(seed: bytes, domain: int, tile_counter: int,
                      size: int) -> np.ndarray:
    """Key-sort ``size`` item ordinals, with ordinal as the tie-break.

    The returned vector is the source-index order: ``output = input[perm]``.
    A key collision therefore has a fully specified result instead of
    depending on a sort implementation.
    """
    if not isinstance(size, int) or isinstance(size, bool):
        raise TypeError("size must be an integer")
    if size < 0:
        raise ValueError("size must be >= 0")
    index = np.arange(size, dtype=np.int64)
    keys = keys64(seed, domain, 0, tile_counter, index, 0)
    return np.lexsort((index, keys)).astype(np.int64, copy=False)


def color_dust_permutation(seed: bytes, tile_counter: int,
                           size: int = 20) -> np.ndarray:
    """Row/address-keyed order for the color dust multiset."""
    return _item_permutation(
        seed, DOMAIN_COLOR_DUST_ORDER, tile_counter, size)


def color_word_zero_mask(seed: bytes, tile_counter: int,
                         n_dust: int) -> np.ndarray:
    """The cmy word '0' state per word site 0..99: True = Y, False = W.

    Domain 9 past the tile's dust draw: site ``i`` reads the key at
    ``u = n_dust + i``, and its MSB (``bits``) chooses Y.
    """
    if not isinstance(n_dust, int) or isinstance(n_dust, bool):
        raise TypeError("n_dust must be an integer")
    if n_dust < 0:
        raise ValueError("n_dust must be >= 0")
    sites = n_dust + np.arange(_WORD_SITES, dtype=np.int64)
    return bits(seed, DOMAIN_COLOR_DUST_ORDER, 0, tile_counter,
                sites, 0).astype(bool)


def cmy7_interleave_permutation(seed: bytes, tile_counter: int,
                                size: int = 10934) -> np.ndarray:
    """CMY7 compound-code source order; ``wire = code[perm]``."""
    return _item_permutation(
        seed, DOMAIN_CMY7_INTERLEAVE, tile_counter, size)


def cmy7_dither_bits(seed: bytes, tile_counter: int,
                     size: int = 10934) -> np.ndarray:
    """CMY7 keyed wire-bit dither, after interleaving and before pack7."""
    if not isinstance(size, int) or isinstance(size, bool):
        raise TypeError("size must be an integer")
    if size < 0:
        raise ValueError("size must be >= 0")
    return bits(
        seed, DOMAIN_CMY7_DITHER, 0, tile_counter,
        np.arange(size, dtype=np.int64), 0)


def color_cell_permutation(seed: bytes, tile_counter: int,
                           size: int = 3976) -> np.ndarray:
    """Color payload-state source order; ``placed = states[perm]``."""
    return _item_permutation(
        seed, DOMAIN_COLOR_CELL_ORDER, tile_counter, size)


def _color_stream_aux(stream: str | int, *, allow_main: bool = True) -> int:
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


def cmy8_dither_bits(seed: bytes, stream: str | int, tile_counter: int,
                     size: int = 3976) -> np.ndarray:
    """One independent payload-bit dither for a CMY8 C/M/Y stream."""
    if not isinstance(size, int) or isinstance(size, bool):
        raise TypeError("size must be an integer")
    if size < 0:
        raise ValueError("size must be >= 0")
    aux = _color_stream_aux(stream, allow_main=False)
    return bits(
        seed, DOMAIN_CMY8_DITHER, aux, tile_counter,
        np.arange(size, dtype=np.int64), 0)


def color_fountain_rows_bits(seed: bytes, stream: str | int,
                             block_index: int, rows,
                             n_cols: int) -> np.ndarray:
    """Color-stream repair rows, using domain 14's packed draw form."""
    aux = _color_stream_aux(stream)
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
    aux = _color_stream_aux(stream)
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

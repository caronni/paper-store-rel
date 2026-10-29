"""Normative reference for the holo v1 keystream — pure Python, stdlib only.

This file IS the printable spec of HOLO-DESIGN §5, as code: a from-scratch
FIPS-197 AES-128 block encryption plus the exact kdf/counter/bit rules of
holo.core.keystream. Any production implementation (the OpenSSL-backed
module included) must match it bit-for-bit; tests/holo/test_keystream.py
cross-checks them and pins FIPS-197 appendix vectors plus frozen holo
golden vectors. Deep-time rule: everything here re-derives from two public
standards (FIPS-197, FIPS 180-4) and this file's own text.

Never optimize this file. Clarity is the contract.

THE DOMAIN TABLE (format-frozen; the counter's byte 0). Address fields
are (aux, major, u, v) per the counter() layout below; plane index =
'CMYK'.index(plane), so the K plane = 3:

  1 payload scramble   aux=plane  major=page   u=cell y    v=cell x
  2 pilot word values  aux=plane  major=0      u=site idx  v=0
  3 filler values      aux=plane  major=page   u=cell y    v=cell x
  4 pilot sites        aux=0      major=0      u=quota idx v=retry
  5 filler sites       aux=0      major=0      u=filler idx v=retry
  6 slot-perm params   aux=0      major=0      u=tile ctr  v=retry
  7 fountain rows      aux=0      major=block  u=row       v=col word
  8 block assignment   aux=0      major=page   u=local tile v=0
  9 color dust order   aux=0      major=tile   u=base ordinal v=0
                       (cmy word '0' sites: u = n_dust + site, Y iff
                       the key's MSB)
 10 CMY7 interleave    aux=0      major=tile   u=code-bit idx v=0
 11 CMY7 dither        aux=0      major=tile   u=wire-bit idx v=0
 12 color cell order   aux=0      major=tile   u=state ordinal v=0
 13 CMY8 dither        aux=stream major=tile   u=cell ordinal v=0
 14 color fountain row aux=stream major=block  u=row v=column word
 15 color block assign aux=stream major=page   u=local tile v=0

Color stream auxiliaries: 0=CMY7 main, 1=CMY8 C, 2=CMY8 M, 3=CMY8 Y.

Two documented exceptions to one-block-per-drawn-value (bulk domains):
domains 7 and 14 pack 128 repair coefficients per block — coefficient c
of (block, row) is bit (c % 128) of the block at v = c // 128, where bit
j of a 16-byte block is
``(byte[j // 8] >> (7 - j % 8)) & 1``, MSB-first; domains 8, 9, 10, 12,
and 15 draw one 64-bit big-endian sort key from block bytes 0..7.

ONE BYTE-ORDER DOCTRINE (format-wide, HOLO-DESIGN §13.12): every
multi-byte integer field is big-endian and every bit string is
MSB-first — bit(addr) is the MSB of block byte 0. No LSB-first form
exists anywhere on the format surface.
"""
from __future__ import annotations

import hashlib

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
PLANE_K = 3   # 'CMYK'.index('K')

COLOR_STREAM_MAIN = 0
COLOR_STREAM_C = 1
COLOR_STREAM_M = 2
COLOR_STREAM_Y = 3


def fountain_coeff_bit(seed: bytes, block_index: int, row: int,
                       column: int) -> int:
    """Repair coefficient (domain 7, packed draw form, MSB-first)."""
    blk = block(seed, DOMAIN_FOUNTAIN_ROW, 0, block_index, row,
                column // 128)
    j = column % 128
    return (blk[j // 8] >> (7 - j % 8)) & 1


def block_assign_key(seed: bytes, page: int, local_tile: int) -> int:
    """64-bit big-endian sort key (domain 8 draw form)."""
    blk = block(seed, DOMAIN_BLOCK_ASSIGN, 0, page, local_tile, 0)
    return int.from_bytes(blk[:8], "big")


def color_dust_order_key(seed: bytes, tile_counter: int,
                         base_ordinal: int) -> int:
    blk = block(
        seed, DOMAIN_COLOR_DUST_ORDER, 0, tile_counter, base_ordinal, 0)
    return int.from_bytes(blk[:8], "big")


def color_word_zero_bit(seed: bytes, tile_counter: int, n_dust: int,
                        site: int) -> int:
    """1 = the cmy word site prints Y for bit '0', 0 = W (domain 9's MSB)."""
    assert n_dust >= 0 and 0 <= site < 100
    return bit(
        seed, DOMAIN_COLOR_DUST_ORDER, 0, tile_counter, n_dust + site, 0)


def cmy7_interleave_key(seed: bytes, tile_counter: int,
                        code_bit_index: int) -> int:
    blk = block(
        seed, DOMAIN_CMY7_INTERLEAVE, 0, tile_counter, code_bit_index, 0)
    return int.from_bytes(blk[:8], "big")


def cmy7_dither_bit(seed: bytes, tile_counter: int,
                    wire_bit_index: int) -> int:
    return bit(
        seed, DOMAIN_CMY7_DITHER, 0, tile_counter, wire_bit_index, 0)


def color_cell_order_key(seed: bytes, tile_counter: int,
                         state_ordinal: int) -> int:
    blk = block(
        seed, DOMAIN_COLOR_CELL_ORDER, 0, tile_counter, state_ordinal, 0)
    return int.from_bytes(blk[:8], "big")


def cmy8_dither_bit(seed: bytes, stream_aux: int, tile_counter: int,
                    cell_ordinal: int) -> int:
    assert COLOR_STREAM_C <= stream_aux <= COLOR_STREAM_Y
    return bit(
        seed, DOMAIN_CMY8_DITHER, stream_aux, tile_counter, cell_ordinal, 0)


def color_fountain_coeff_bit(seed: bytes, stream_aux: int,
                             block_index: int, row: int,
                             column: int) -> int:
    assert COLOR_STREAM_MAIN <= stream_aux <= COLOR_STREAM_Y
    blk = block(
        seed, DOMAIN_COLOR_FOUNTAIN_ROW, stream_aux, block_index, row,
        column // 128)
    j = column % 128
    return (blk[j // 8] >> (7 - j % 8)) & 1


def color_block_assign_key(seed: bytes, stream_aux: int, page: int,
                           local_tile: int) -> int:
    assert COLOR_STREAM_MAIN <= stream_aux <= COLOR_STREAM_Y
    blk = block(
        seed, DOMAIN_COLOR_BLOCK_ASSIGN, stream_aux, page, local_tile, 0)
    return int.from_bytes(blk[:8], "big")

# ------------------------------------------------------------ AES-128 core
# S-box generated from the FIPS-197 definition (multiplicative inverse in
# GF(2^8) followed by the affine transform) — computed at import so the
# table itself is derived, not transcribed.


def _build_sbox() -> list[int]:
    # GF(2^8) inverse via exp/log tables over generator 3
    exp = [0] * 510
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        # multiply by generator 0x03 = x * 2 ^ x
        x ^= (x << 1) ^ (0x11B if x & 0x80 else 0)
        x &= 0xFF
    for i in range(255, 510):
        exp[i] = exp[i - 255]
    sbox = [0] * 256
    for a in range(256):
        inv = 0 if a == 0 else exp[255 - log[a]]
        b = inv
        r = 0
        for k in range(8):
            r |= (((b >> k) ^ (b >> ((k + 4) % 8)) ^ (b >> ((k + 5) % 8))
                   ^ (b >> ((k + 6) % 8)) ^ (b >> ((k + 7) % 8))
                   ^ (0x63 >> k)) & 1) << k
        sbox[a] = r
    return sbox


_SBOX = _build_sbox()


def _xtime(a: int) -> int:
    a <<= 1
    return (a ^ 0x1B) & 0xFF if a & 0x100 else a


def _expand_key(key: bytes) -> list[list[int]]:
    """AES-128 key schedule: 11 round keys of 16 bytes each."""
    assert len(key) == 16
    words = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    rcon = 1
    for i in range(4, 44):
        w = list(words[i - 1])
        if i % 4 == 0:
            w = w[1:] + w[:1]                      # RotWord
            w = [_SBOX[b] for b in w]              # SubWord
            w[0] ^= rcon
            rcon = _xtime(rcon)
        words.append([a ^ b for a, b in zip(words[i - 4], w)])
    return [sum(words[4 * r:4 * r + 4], []) for r in range(11)]


def aes128_encrypt_block(key: bytes, block: bytes) -> bytes:
    """One AES-128 block encryption, FIPS-197 §5.1.

    State is column-major: state[r][c] = input[4*c + r].
    """
    assert len(block) == 16
    rk = _expand_key(key)
    s = [[block[4 * c + r] for c in range(4)] for r in range(4)]

    def add_round_key(n: int) -> None:
        for c in range(4):
            for r in range(4):
                s[r][c] ^= rk[n][4 * c + r]

    def sub_shift() -> None:
        for r in range(4):
            row = [_SBOX[s[r][(c + r) % 4]] for c in range(4)]  # SubBytes +
            s[r] = row                                          # ShiftRows

    def mix_columns() -> None:
        for c in range(4):
            a0, a1, a2, a3 = (s[r][c] for r in range(4))
            t = a0 ^ a1 ^ a2 ^ a3
            s[0][c] = a0 ^ t ^ _xtime(a0 ^ a1)
            s[1][c] = a1 ^ t ^ _xtime(a1 ^ a2)
            s[2][c] = a2 ^ t ^ _xtime(a2 ^ a3)
            s[3][c] = a3 ^ t ^ _xtime(a3 ^ a0)

    add_round_key(0)
    for rnd in range(1, 10):
        sub_shift()
        mix_columns()
        add_round_key(rnd)
    sub_shift()
    add_round_key(10)
    return bytes(s[r][c] for c in range(4) for r in range(4))


# ------------------------------------------------- keystream rules (spec)

KDF_PREFIX = b"holo/v1|"


def kdf(seed: bytes) -> bytes:
    return hashlib.sha256(KDF_PREFIX + seed).digest()[:16]


def counter(domain: int, aux: int, major: int, u: int, v: int) -> bytes:
    assert 0 <= domain <= 0xFF and 0 <= aux <= 0xFF
    assert 0 <= major < (1 << 24) and 0 <= u < (1 << 32) and 0 <= v < (1 << 32)
    return bytes([domain, aux]) + major.to_bytes(3, "big") \
        + u.to_bytes(4, "big") + v.to_bytes(4, "big") + b"\x00\x00\x00"


def block(seed: bytes, domain: int, aux: int, major: int, u: int,
          v: int) -> bytes:
    return aes128_encrypt_block(kdf(seed), counter(domain, aux, major, u, v))


def bit(seed: bytes, domain: int, aux: int, major: int, u: int,
        v: int) -> int:
    return block(seed, domain, aux, major, u, v)[0] >> 7


def bounded_draw(seed: bytes, domain: int, u: int, bound: int) -> int:
    """The spec'd rejection rule: scan block bytes 0..15 at v=0,1,2,...;
    accept the first byte b < 256 - (256 % bound); value = b % bound."""
    assert 1 <= bound <= 256
    limit = 256 - (256 % bound)
    v = 0
    while True:
        blk = block(seed, domain, 0, 0, u, v)
        for b in blk:
            if b < limit:
                return b % bound
        v += 1


def slot_perm_param(seed: bytes, tile_counter: int, n_slots: int
                    ) -> tuple[int, int]:
    """Affine slot-perm parameters over the transmitted positions: scan
    unbiased 16-bit values (big-endian word pairs of successive blocks at
    v = 0, 1, ...); a = first with gcd(value, n_slots) == 1, b = the next
    admissible value."""
    import math
    limit = 65536 - (65536 % n_slots)
    a = b = None
    v = 0
    while b is None:
        blk = block(seed, DOMAIN_SLOT_PERM, 0, 0, tile_counter, v)
        for i in range(0, 16, 2):
            w = (blk[i] << 8) | blk[i + 1]
            if w >= limit:
                continue
            val = w % n_slots
            if a is None:
                if math.gcd(val, n_slots) == 1:
                    a = val
            elif b is None:
                b = val
        v += 1
    return a, b

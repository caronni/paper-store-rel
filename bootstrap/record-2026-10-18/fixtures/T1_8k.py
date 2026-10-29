"""Pure-Python bit-exact reference for the covert keystream chain (spec-as-code).

Every covert stream in the codec flows through modulation.rng:

    BLAKE2b(seed + label, digest_size=16) -> int.from_bytes(digest, "little")
    -> numpy Philox(key=...) (no SeedSequence) -> Generator.integers(...)

Until this module existed, the normative definition of that stream lived in
numpy internals: bit-exactness of every printed sheet depends on numpy's
dtype-dependent bounded-draw consumption (the e012 phantom-payload incident —
integers() without dtype=np.uint8 forks the stream — is the measured proof
that a consumption mismatch reads as 50% noise under clean pilots). For a
printed archive that must decode decades from now, "whatever numpy does" is
not a spec. This module IS the spec: pure Python, stdlib only (hashlib), no
numpy import, verified byte-for-byte against numpy 2.4.6 and 2.5.0 by
tests/test_keystream_ref.py, with golden vectors for the e016 volume seed
frozen in tests/golden_keystream_vectors.json.

NOT a format change: nothing here is called by codec paths; modulation.rng
stays the production implementation. The modulation.py TODO(prod) about
swapping to per-cell-address AES-CTR keying remains a separate format-axis
(layout_version) decision.

Measured consumption rules (empirically pinned against numpy, all draw forms
below re-verified by the test suite — Generator semantics, endpoint=False):

  Philox-4x64-10 bit generator, key from a 128-bit int:
    key words  = (key & 2^64-1, key >> 64)              # little-endian split
    counter    = [0, 0, 0, 0], incremented (with carry) BEFORE each block
    block      = philox4x64_10(counter, key) -> 4 words, consumed in order
    next32     = each 64-bit word yields its LOW half first, then the high
                 half; the pending half-word PERSISTS across integers() calls
                 (bit-generator state), unlike the per-call buffers below.

  Generator.integers(low, high) bounded draws use LEMIRE rejection (the
  legacy masked-rejection path belongs to RandomState, not Generator):
    dtype=np.uint8:  bytes come from a per-CALL buffer over next32 words,
                     low byte first (buf >>= 8 between lanes, 4 lanes/word);
                     value = (byte * rng_excl) >> 8, reject while
                     (m & 0xFF) < (0xFF - rng) % rng_excl.
                     rng == 255 -> raw bytes; rng == 0 -> constant, and the
                     call consumes NOTHING.
    default (int64): rng <= 2^32-1 routes through 32-bit draws:
                     value = (next32 * rng_excl) >> 32, reject while
                     (m & 0xFFFFFFFF) < (2^32-1 - rng) % rng_excl.
                     rng > 2^32-1 uses the same construction on next64;
                     rng == 2^32-1 / 2^64-1 -> raw next32/next64;
                     rng == 0 -> constant, consumes nothing.
    Arrays fill in C order; a scalar call (size=None) consumes like size=1.

Codec streams covered (the wrapper functions below are the label registry):
    payload keystream   bytes([plane]) + page_le32       u8   (0, 2)
    pilot sites v1      b"pilot-sites"                   i64  (0, 6, (10,10,2))
    pilot sites v2-v4   b"pilot-sites-v2" (SHARED label) i64  (0, 6, (10,10,2))
    pilot values v2-v4  b"pilot-values-v{2,3,4}/"+plane  i64  (0, 2, 100)
    ldpc construction   seed=b"ldpc-v1/<rate_id>",       i64  scalars (0, i+1)
                        label=b"eira-H/restart<R>"            + (0,mb,d)/(0,z,d)
                        (volume-seed INDEPENDENT: the ladder label is the seed)
    fountain-v1 rows    b"fountain-v1/row/" [+ level:1   i64  (0, 2, K_b)
                        iff n_levels > 1] + block_le32
                        + i_le32 (single-level = frozen e016 form)
    dust sites v4       b"dust-sites-v4"                 i64  partial FY
                        (explicit dtype=np.int64 == the       scalars (i, n)
                        default-dtype stream)
    dust states v4      b"dust-states-v4" + page_le32    u8   (0, 8, M), then
                        + tile_le32                           FY scalars (0,i+1)
    symbol keystream    b"symks/<encoding_id>/pg"+page_le32   u8 (0, n_states)
    e016 volume data    b"e016/data" (gen_e016.make_data)     u8 (0, 256)

Out of scope (documented, not pinned): the freeform-RLL field sampler's
consumption (rll-i2w3 is not data-bearing; motif-B2 data modes are a 010
no-go), and every non-integers Generator method — codec paths use none.
"""
from __future__ import annotations

import hashlib

_M64 = (1 << 64) - 1
_M32 = (1 << 32) - 1

# Random123 Philox-4x64 constants (multipliers + Weyl key increments).
_PHILOX_M0 = 0xD2E7470EE14C6C93
_PHILOX_M1 = 0xCA5A826395121157
_PHILOX_W0 = 0x9E3779B97F4A7C15
_PHILOX_W1 = 0xBB67AE8584CAA73B


def philox4x64_10(ctr: tuple[int, int, int, int],
                  key: tuple[int, int]) -> tuple[int, int, int, int]:
    """One Philox-4x64 block: 10 rounds, key bumped before rounds 2..10."""
    c0, c1, c2, c3 = ctr
    k0, k1 = key
    for r in range(10):
        if r:
            k0 = (k0 + _PHILOX_W0) & _M64
            k1 = (k1 + _PHILOX_W1) & _M64
        p0 = _PHILOX_M0 * c0
        p1 = _PHILOX_M1 * c2
        c0, c1, c2, c3 = ((p1 >> 64) ^ c1 ^ k0, p1 & _M64,
                          (p0 >> 64) ^ c3 ^ k1, p0 & _M64)
    return (c0, c1, c2, c3)


def philox_key(seed: bytes, label: bytes) -> int:
    """The modulation.rng keying step: BLAKE2b-128(seed+label), little-endian."""
    return int.from_bytes(
        hashlib.blake2b(seed + label, digest_size=16).digest(), "little")


class PhiloxRef:
    """numpy.random.Philox(key=int) bit-generator state machine.

    State = 256-bit counter + pending block words + pending 32-bit half-word.
    All three persist across integers() calls; only the uint8 byte buffer in
    GeneratorRef is per-call."""

    def __init__(self, key128: int) -> None:
        if not 0 <= key128 < (1 << 128):
            raise ValueError("key must be a 128-bit unsigned int")
        self._key = (key128 & _M64, (key128 >> 64) & _M64)
        self._ctr = [0, 0, 0, 0]
        self._buf: list[int] = []
        self._has32 = False
        self._pending32 = 0

    def next64(self) -> int:
        if not self._buf:
            self._ctr[0] = (self._ctr[0] + 1) & _M64
            if self._ctr[0] == 0:                      # carry chain
                self._ctr[1] = (self._ctr[1] + 1) & _M64
                if self._ctr[1] == 0:
                    self._ctr[2] = (self._ctr[2] + 1) & _M64
                    if self._ctr[2] == 0:
                        self._ctr[3] = (self._ctr[3] + 1) & _M64
            self._buf = list(philox4x64_10(tuple(self._ctr), self._key))
        return self._buf.pop(0)

    def next32(self) -> int:
        if self._has32:
            self._has32 = False
            return self._pending32
        word = self.next64()
        self._has32 = True
        self._pending32 = (word >> 32) & _M32
        return word & _M32


class GeneratorRef:
    """Generator.integers(low, high, size, dtype) for the two codec dtypes."""

    def __init__(self, key128: int) -> None:
        self.bitgen = PhiloxRef(key128)

    def integers(self, low: int, high: int, size: int | None = None,
                 dtype: str = "int64") -> int | list[int]:
        """Mirror of numpy Generator.integers (endpoint=False, C-order flat).

        size is the flat element count (callers reshape); size=None returns a
        scalar drawn identically to size=1. Only the codec's parameter region
        is implemented: 0 <= low < high, dtype in {"uint8", "int64"}."""
        if not 0 <= low < high:
            raise ValueError(f"need 0 <= low < high, got [{low}, {high})")
        cnt = 1 if size is None else int(size)
        if cnt < 0:
            raise ValueError("size must be >= 0")
        if dtype == "uint8":
            if high > 256:
                raise ValueError("uint8 high bound must be <= 256")
            out = self._fill_uint8(low, high - 1 - low, cnt)
        elif dtype == "int64":
            if high > (1 << 63):
                raise ValueError("int64 high bound must be <= 2^63")
            out = self
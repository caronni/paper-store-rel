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
            out = self._fill_int64(low, high - 1 - low, cnt)
        else:
            raise ValueError(f"unsupported dtype {dtype!r} (codec uses "
                             "uint8 and the int64 default only)")
        return out[0] if size is None else out

    def _fill_uint8(self, off: int, rng: int, cnt: int) -> list[int]:
        if rng == 0:
            return [off] * cnt                        # consumes nothing
        bitgen = self.bitgen
        buf = 0
        bcnt = 0                                      # per-CALL byte buffer

        def next_byte() -> int:
            nonlocal buf, bcnt
            if not bcnt:
                buf = bitgen.next32()
                bcnt = 3
            else:
                buf >>= 8
                bcnt -= 1
            return buf & 0xFF

        if rng == 0xFF:                               # Lemire needs rng < 255
            return [(off + next_byte()) & 0xFF for _ in range(cnt)]
        rng_excl = rng + 1
        threshold = (0xFF - rng) % rng_excl
        out = []
        for _ in range(cnt):
            m = next_byte() * rng_excl
            if (m & 0xFF) < rng_excl:
                while (m & 0xFF) < threshold:
                    m = next_byte() * rng_excl
            out.append(off + (m >> 8))
        return out

    def _fill_int64(self, off: int, rng: int, cnt: int) -> list[int]:
        if rng == 0:
            return [off] * cnt                        # consumes nothing
        bitgen = self.bitgen
        if rng <= _M32:
            if rng == _M32:
                return [off + bitgen.next32() for _ in range(cnt)]
            rng_excl = rng + 1
            threshold = (_M32 - rng) % rng_excl
            out = []
            for _ in range(cnt):
                m = bitgen.next32() * rng_excl
                if (m & _M32) < rng_excl:
                    while (m & _M32) < threshold:
                        m = bitgen.next32() * rng_excl
                out.append(off + (m >> 32))
            return out
        if rng == _M64:
            return [off + bitgen.next64() for _ in range(cnt)]
        rng_excl = rng + 1
        threshold = (_M64 - rng) % rng_excl
        out = []
        for _ in range(cnt):
            m = bitgen.next64() * rng_excl
            if (m & _M64) < rng_excl:
                while (m & _M64) < threshold:
                    m = bitgen.next64() * rng_excl
            out.append(off + (m >> 64))
        return out


def rng_ref(seed: bytes, label: bytes) -> GeneratorRef:
    """Pure-Python mirror of modulation.rng(seed, label)."""
    return GeneratorRef(philox_key(seed, label))


# ---------------------------------------------------------------------------
# Codec-stream label registry + draw forms (executable documentation).
# Frozen format constants are restated here ON PURPOSE — this module must
# stay meaningful with the rest of the package deleted; the tests assert it
# agrees with the live modules.
# ---------------------------------------------------------------------------

# payload-keystream plane index convention (encodings._plane_index), distinct
# from pilots.PLANE_ID (the BCH word field): K = 3 here.
PLANE_KEYSTREAM_INDEX: dict[str, int] = {"C": 0, "M": 1, "Y": 2, "K": 3}


def payload_keystream_label(plane_index: int, page: int) -> bytes:
    return bytes([plane_index & 0xFF]) + page.to_bytes(4, "little")


def payload_keystream_bits(seed: bytes, plane_index: int, page: int,
                           n_bits: int) -> list[int]:
    """modulation.keystream: integers(0, 2, size=shape, dtype=np.uint8),
    C-order flat prefix of length n_bits."""
    g = rng_ref(seed, payload_keystream_label(plane_index, page))
    return g.integers(0, 2, n_bits, dtype="uint8")


def pilot_sites_label(layout_version: int) -> bytes:
    """v1 = b"pilot-sites"; v2/v3/v4 = b"pilot-sites-v2" (deliberately
    shared — pilots.py contract: no per-version site labels exist)."""
    if layout_version == 1:
        return b"pilot-sites"
    if layout_version in (2, 3, 4):
        return b"pilot-sites-v2"
    raise ValueError(f"unknown layout_version {layout_version}")


def pilot_site_offsets(seed: bytes, layout_version: int = 3,
                       blocks: int = 10, block_cells: int = 6) -> list[int]:
    """In-block (dy, dx) offsets: integers(0, block_cells, size=(blocks,
    blocks, 2)) at DEFAULT dtype, returned C-order flat (len 200). The
    (10, 10, 2) shape is shared by v1 (64//6 == 10) and p60b6 (60//6)."""
    g = rng_ref(seed, pilot_sites_label(layout_version))
    return g.integers(0, block_cells, blocks * blocks * 2)


def pilot_values_label(layout_version: int, plane: str) -> bytes:
    """v4 words are luma-channel objects: plane is always "K" there
    (PILOTS-DESIGN §16.2) — the v4/C,M,Y streams do not exist."""
    if plane not in PLANE_KEYSTREAM_INDEX:
        raise ValueError(f"unknown plane {plane!r}")
    if layout_version == 4 and plane != "K":
        raise ValueError("v4 pilot words are luma objects: plane is 'K'")
    if layout_version in (2, 3, 4):
        return (f"pilot-values-v{layout_version}/".encode()
                + plane.encode())
    raise ValueError(f"no value keystream for layout_version {layout_version}")


def pilot_value_bits(seed: bytes, layout_version: int, plane: str,
                     sites_per_tile: int = 100) -> list[int]:
    """pilots.value_keystream_tile: integers(0, 2, 100) at DEFAULT dtype —
    the dtype kwarg would fork the stream; this is the frozen form."""
    g = rng_ref(seed, pilot_values_label(layout_version, plane))
    return g.integers(0, 2, sites_per_tile)


def ldpc_construction_rng(rate_id: str, restart: int) -> GeneratorRef:
    """ldpc._draw_h_blocks generator: seed = the LADDER LABEL ITSELF
    (b"ldpc-v1/<rate_id>"), label = b"eira-H/restart<R>" — the H matrix is
    independent of any volume seed. Consumption: Fisher-Yates scalars
    integers(0, i+1) for i = m_bits-1 .. 1, then per column attempt
    integers(0, mb, size=d) + integers(0, z, size=d)."""
    return rng_ref(b"ldpc-v1/" + rate_id.encode(),
                   b"eira-H/restart" + str(restart).encode())


def fisher_yates(g: GeneratorRef, m: int) -> list[int]:
    """ldpc._fisher_yates on the reference generator (frozen derivation)."""
    pi = list(range(m))
    for i in range(m - 1, 0, -1):
        j = g.integers(0, i + 1)
        pi[i], pi[j] = pi[j], pi[i]
    return pi


def fountain_row_label(block: int, i: int, level: int | None = None) -> bytes:
    """Single-level volumes (e016) omit the level byte — frozen form; the
    level byte enters ONLY for n_levels > 1 (layout_version-4 MLC)."""
    lvl = b"" if level is None else bytes([level])
    return (b"fountain-v1/row/" + lvl + block.to_bytes(4, "little")
            + i.to_bytes(4, "little"))


def dust_sites_label() -> bytes:
    """dust.dust_positions_tile: partial Fisher-Yates over the non-pilot
    cells — scalars integers(i, n, dtype=np.int64) for i = 0..M-1 (the
    explicit np.int64 IS the default dtype: same stream)."""
    return b"dust-sites-v4"


def dust_states_label(page: int, tile_index: int) -> bytes:
    """dust.dust_states_tile: integers(0, 8, M, dtype=np.uint8), then the
    quota fix-up's full Fisher-Yates scalars (0, i+1) on the SAME stream."""
    return (b"dust-states-v4" + page.to_bytes(4, "little")
            + tile_index.to_bytes(4, "little"))


def fountain_row_bits(seed: bytes, block: int, i: int,
                      k_block: int) -> list[int]:
    """fountain.generator_row repair row (i >= K_b): integers(0, 2, K_b) at
    DEFAULT dtype. rng == 1 draws one 32-bit word per bit with no rejection,
    so any prefix is independent of k_block."""
    g = rng_ref(seed, fountain_row_label(block, i))
    return g.integers(0, 2, k_block)


def symbol_keystream_label(encoding_id: str, page: int) -> bytes:
    return (b"symks/" + encoding_id.encode() + b"/pg"
            + page.to_bytes(4, "little"))


def symbol_keystream(seed: bytes, encoding_id: str, page: int,
                     n_cells: int, n_states: int) -> list[int]:
    """encodings.key_symbols for alphabet encodings (n_states > 2):
    integers(0, n_states, size=shape, dtype=np.uint8), C-order flat."""
    g = rng_ref(seed, symbol_keystream_label(encoding_id, page))
    return g.integers(0, n_states, n_cells, dtype="uint8")

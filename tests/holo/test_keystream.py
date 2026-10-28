"""holo v1 keystream: FIPS-197 anchors, reference==production, goldens.

GOLDEN VECTORS (bump-don't-edit): the digests below pin the printed
format's keystream. A mismatch means the keystream changed — that is a
format fork, never a test to update.
"""
import hashlib
import math

import numpy as np
import pytest


from holo.core import keystream as prod
from holo.core import keystream_spec as ref

SEED = b"holo/v1/c2-r0550/3328x2304"

# re-frozen 2026-07-19 (pre-print identity forks: §13.9 seeds embed
# coding+geometry; §13.12 bit draws MSB-first — slot-perm is byte-level
# and did NOT move across §13.12, a deliberate cross-check); sha256 of
# the named byte streams
GOLDEN = {
    # 256 payload bits (plane 3, page 0, cells y=0, x=0..255), packbits
    "payload-256": "cf3943f45be5b668fb87799bafa71df2"
                   "bf858eb2fb06fb6df03498501069b78f",
    # 100 pilot-value scramble bits (plane 3, sites 0..99), packbits
    "pilot-values-100": "cfa8f309811d523137b3ff9805ae5d75"
                        "5b1ebf55017d67d0429de870f792cb4e",
    # (a, b) for tiles 0..15 at T=3996, int64 bytes a then b
    "slot-perm-16": "025219fdc0b082e73e389d8640b9b30c"
                    "79eff8bf48bc3963f92490cbe57a4b18",
    # 1872 domain-8 uint64 BE keys (page 139, local tiles 0..1871)
    "block-assign-1872": "5f5da9ce386c164d2f106e4a2f02ecf"
                         "b8b521435e95962c46217498c6d3a62ec",
}


def test_spec_constants_equal_production():
    """The printable spec's domain/plane table must never drift from the
    production module (both are declared spec surfaces)."""
    for name in ("DOMAIN_PAYLOAD", "DOMAIN_PILOT_VALUES",
                 "DOMAIN_FILLER_VALUES", "DOMAIN_PILOT_SITES",
                 "DOMAIN_FILLER_SITES", "DOMAIN_SLOT_PERM",
                 "DOMAIN_FOUNTAIN_ROW", "DOMAIN_BLOCK_ASSIGN", "PLANE_K"):
        assert getattr(ref, name) == getattr(prod, name), name


def test_fips_197_vectors():
    key = bytes(range(16))
    pt = bytes.fromhex("00112233445566778899aabbccddeeff")
    assert ref.aes128_encrypt_block(key, pt).hex() == \
        "69c4e0d86a7b0430d8cdb78070b4c55a"
    key2 = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
    pt2 = bytes.fromhex("3243f6a8885a308d313198a2e0370734")
    assert ref.aes128_encrypt_block(key2, pt2).hex() == \
        "3925841d02dc09fbdc118597196a0b32"


def test_reference_equals_production_blocks():
    cases = [(1, 3, 0, 0, 0), (1, 3, 2, 100, 200), (2, 3, 0, 57, 0),
             (3, 3, 139, 3327, 2303), (4, 0, 0, 99, 0),
             (6, 0, 0, 261143, 0), (7, 0, 63, 4095, 4095),
             (8, 0, 139, 1871, 0)]
    for dom, aux, major, u, v in cases:
        assert ref.block(SEED, dom, aux, major, u, v) == \
            prod.blocks(SEED, dom, aux, major, u, v)[0].tobytes()
        assert ref.bit(SEED, dom, aux, major, u, v) == \
            int(prod.bits(SEED, dom, aux, major, u, v)[0])


def test_bounded_draws_match_and_range():
    for bound in (2, 6, 7, 49, 64, 100, 256):
        us = [0, 1, 42, 99]
        got = prod.bounded_draws(SEED, prod.DOMAIN_PILOT_SITES, us, bound)
        for i, u in enumerate(us):
            r = ref.bounded_draw(SEED, prod.DOMAIN_PILOT_SITES, u, bound)
            assert r == int(got[i])
            assert 0 <= r < bound


def test_slot_perm_reference_match_gcd_bijection():
    T = 4096 - 100
    tcs = [0, 1, 7, 1871, 261143]
    a, b = prod.slot_perm_params(SEED, tcs, T)
    j = np.arange(T)
    for i, tc in enumerate(tcs):
        assert ref.slot_perm_param(SEED, tc, T) == (int(a[i]), int(b[i]))
        assert math.gcd(int(a[i]), T) == 1
        p = (int(a[i]) * j + int(b[i])) % T
        assert np.unique(p).size == T


def test_block_assign_keys_reference_match():
    pages = (0, 1, 63, 139)
    local_tiles = np.array([0, 1, 17, 839, 1871], dtype=np.int64)
    for page in pages:
        got = prod.keys64(SEED, prod.DOMAIN_BLOCK_ASSIGN, 0, page,
                          local_tiles, 0)
        expected = np.array([
            ref.block_assign_key(SEED, page, int(local_tile))
            for local_tile in local_tiles
        ], dtype=np.uint64)
        assert np.array_equal(got, expected)


def test_counter_field_range_enforced():
    with pytest.raises(ValueError):
        prod.counters(1, 0, 1 << 24, 0, 0)
    with pytest.raises(ValueError):
        prod.counters(1, 0, 0, -1, 0)
    with pytest.raises(ValueError):
        prod.counters(300, 0, 0, 0, 0)
    with pytest.raises(ValueError):
        prod.kdf(b"")


def test_payload_field_shape_balance_determinism():
    f = prod.payload_bits(SEED, 3, 0, (64, 128))
    assert f.shape == (64, 128) and f.dtype == np.uint8
    assert set(np.unique(f)) <= {0, 1}
    assert abs(float(f.mean()) - 0.5) < 0.05
    assert np.array_equal(f, prod.payload_bits(SEED, 3, 0, (64, 128)))
    # different plane / page / seed all fork the stream
    assert not np.array_equal(f, prod.payload_bits(SEED, 0, 0, (64, 128)))
    assert not np.array_equal(f, prod.payload_bits(SEED, 3, 1, (64, 128)))
    assert not np.array_equal(
        f, prod.payload_bits(b"holo/v1/c3-r0550/2240x1536", 3, 0, (64, 128)))


def test_golden_payload():
    b = prod.bits(SEED, prod.DOMAIN_PAYLOAD, 3, 0, 0, np.arange(256))
    assert hashlib.sha256(np.packbits(b).tobytes()).hexdigest() == \
        GOLDEN["payload-256"]


def test_golden_pilot_values():
    b = prod.bits(SEED, prod.DOMAIN_PILOT_VALUES, 3, 0, np.arange(100), 0)
    assert hashlib.sha256(np.packbits(b).tobytes()).hexdigest() == \
        GOLDEN["pilot-values-100"]


def test_golden_slot_perm():
    a, b = prod.slot_perm_params(SEED, np.arange(16), 4096 - 100)
    assert hashlib.sha256(a.tobytes() + b.tobytes()).hexdigest() == \
        GOLDEN["slot-perm-16"]


def test_golden_block_assign_keys():
    keys = prod.keys64(SEED, prod.DOMAIN_BLOCK_ASSIGN, 0, 139,
                       np.arange(1872), 0)
    canonical = keys.astype(">u8", copy=False).tobytes()
    assert hashlib.sha256(canonical).hexdigest() == \
        GOLDEN["block-assign-1872"]

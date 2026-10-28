"""Modulation-independent, compound LDPC frame contracts."""

import hashlib

import numpy as np
import pytest

from holo.core.ldpc import frame
from holo.core.ldpc.construct import LADDER
from holo.core.ldpc.decode import encode
from holo.core.ldpc.tile import CRC_BITS, crc32_bits


CMY7_BANK = frame.FecBankProfile(
    "cmy7-p120-v0",
    (
        frame.FecChildProfile("r0550", 0),
        frame.FecChildProfile("r0625", 677),
        frame.FecChildProfile("r0625", 677),
    ),
)

CMY8_BANKS = {
    "C": frame.FecBankProfile(
        "cmy8-p120-C-v0", (frame.FecChildProfile("r0550", 120),)
    ),
    "M": frame.FecBankProfile(
        "cmy8-p120-M-v0", (frame.FecChildProfile("r0550", 120),)
    ),
    "Y": frame.FecBankProfile(
        "cmy8-p120-Y-v0", (frame.FecChildProfile("r0547", 120),)
    ),
}

# sha256 over the uint8[10934] transmitted vector for
# _cmy7_frozen_user_vector().  This externally pins the provisional frame
# split and all three independently frozen mother-code encodings.
CMY7_TRANSMITTED_SHA256 = (
    "f9dee9842135e76f9c1d3c1e4a897793"
    "2f4b31a0f6cd6bd9a6de0fb5cb189292"
)
CMY7_USER_CRC32 = bytes.fromhex("f7f7fbb9")


def _clean_llrs(bits: np.ndarray, magnitude: float = 8.0) -> np.ndarray:
    return (2.0 * bits.astype(np.float64) - 1.0) * magnitude


def _encode_raw_frame(
    frame_bits: np.ndarray,
    bank: frame.FecBankProfile = CMY7_BANK,
) -> np.ndarray:
    """Test-only encoder for syndrome-valid frames with deliberately bad CRC."""
    parts = []
    offset = 0
    for child in bank.children:
        spec = LADDER[child.code_id]
        active = child.active_information_bits
        info = np.zeros(spec.k_bits, dtype=np.uint8)
        info[:active] = frame_bits[offset:offset + active]
        offset += active
        codeword = encode(info, child.code_id)
        parts.append(codeword[frame.transmitted_positions(child)])
    assert offset == frame_bits.size
    return np.concatenate(parts)


def _cmy7_frozen_user_vector() -> tuple[np.uint8, np.ndarray, np.ndarray]:
    """Independent deterministic metadata/fountain fixture for v0."""
    metadata = np.uint8(1)
    fountain = np.unpackbits(np.frombuffer(
        hashlib.shake_256(b"holo/cmy7-p120-v0/frame-vector").digest(747),
        dtype=np.uint8,
    ))[:5973]
    user = np.concatenate((np.asarray([metadata], dtype=np.uint8), fountain))
    assert user.size == CMY7_BANK.user_bits
    return metadata, fountain, user


def test_cmy7_bank_arithmetic_is_exact():
    assert [child.active_information_bits for child in CMY7_BANK.children] == [
        2240, 1883, 1883]
    assert [child.transmitted_bits for child in CMY7_BANK.children] == [
        4096, 3419, 3419]
    assert CMY7_BANK.active_information_bits == 6006
    assert CMY7_BANK.transmitted_bits == 10934
    assert CMY7_BANK.user_bits == 5974
    assert CMY7_BANK.user_bits - 1 == 5973


def test_cmy7_frame_boundaries_and_frozen_transmitted_digest():
    metadata, fountain, user = _cmy7_frozen_user_vector()
    transmitted = frame.encode_frame(user, CMY7_BANK)

    a = transmitted[:4096]
    b = transmitted[4096:4096 + 3419]
    c = transmitted[4096 + 3419:]
    crc = crc32_bits(user)
    assert np.array_equal(
        crc, np.unpackbits(np.frombuffer(CMY7_USER_CRC32, dtype=np.uint8))
    )

    # These are direct observations of the systematic prefixes on paper,
    # not a decode through the implementation under test.
    assert a[0] == metadata
    assert np.array_equal(a[1:2240], fountain[:2239])
    assert np.array_equal(b[:1883], fountain[2239:4122])
    assert np.array_equal(c[:1851], fountain[4122:5973])
    assert np.array_equal(c[1851:1883], crc)

    assert hashlib.sha256(
        transmitted.tobytes(order="C")
    ).hexdigest() == CMY7_TRANSMITTED_SHA256


def test_transmitted_positions_are_active_prefix_plus_all_parity():
    for child in CMY7_BANK.children:
        spec = LADDER[child.code_id]
        positions = frame.transmitted_positions(child)
        active = child.active_information_bits
        assert positions.size == child.transmitted_bits
        assert np.array_equal(positions[:active], np.arange(active))
        assert np.array_equal(
            positions[active:], np.arange(spec.k_bits, spec.n_bits))


def test_compound_frame_clean_roundtrip():
    rng = np.random.default_rng(2207)
    user = rng.integers(0, 2, CMY7_BANK.user_bits, dtype=np.uint8)
    transmitted = frame.encode_frame(user, CMY7_BANK)
    result = frame.decode_frame(_clean_llrs(transmitted), CMY7_BANK)

    assert result.ok
    assert result.crc_invoked and result.crc_ok is True
    assert all(child.syndrome_ok and child.n_iters == 0
               for child in result.children)
    assert np.array_equal(result.certified_user_bits, user)


@pytest.mark.parametrize("failed_child", range(3), ids=("A", "B", "C"))
def test_child_syndrome_failure_never_invokes_shared_crc(
    monkeypatch, failed_child
):
    rng = np.random.default_rng(2208)
    user = rng.integers(0, 2, CMY7_BANK.user_bits, dtype=np.uint8)
    transmitted = frame.encode_frame(user, CMY7_BANK)
    llrs = _clean_llrs(transmitted)
    child_offset = sum(
        child.transmitted_bits for child in CMY7_BANK.children[:failed_child]
    )
    llrs[child_offset] *= -1.0

    calls = 0

    def watched_crc(bits):
        nonlocal calls
        calls += 1
        return crc32_bits(bits)

    monkeypatch.setattr(frame, "crc32_bits", watched_crc)
    result = frame.decode_frame(llrs, CMY7_BANK, max_iters=0)

    assert not result.ok
    assert not result.children[failed_child].syndrome_ok
    assert all(
        outcome.syndrome_ok
        for index, outcome in enumerate(result.children)
        if index != failed_child
    )
    assert result.crc_invoked is False and result.crc_ok is None
    assert result.certified_user_bits is None
    assert calls == 0


@pytest.mark.parametrize("stream", ("C", "M", "Y"))
def test_cmy8_independent_single_child_bank_arithmetic_and_roundtrip(stream):
    bank = CMY8_BANKS[stream]
    child, = bank.children
    expected_code = "r0547" if stream == "Y" else "r0550"

    assert child.code_id == expected_code
    assert child.shortened_info_tail == 120
    assert child.transmitted_bits == 3976
    assert child.active_information_bits == 2120
    assert bank.transmitted_bits == 3976
    assert bank.active_information_bits == 2120
    assert bank.user_bits == 2088
    assert bank.user_bits - 1 == 2087

    rng = np.random.default_rng(0xC800 + ord(stream))
    user = rng.integers(0, 2, bank.user_bits, dtype=np.uint8)
    transmitted = frame.encode_frame(user, bank)
    result = frame.decode_frame(_clean_llrs(transmitted), bank)

    assert transmitted.shape == (3976,)
    assert np.array_equal(transmitted[:2088], user)
    assert np.array_equal(transmitted[2088:2120], crc32_bits(user))
    assert result.ok and result.crc_invoked and result.crc_ok is True
    assert len(result.children) == 1
    assert result.children[0].code_id == expected_code
    assert result.children[0].syndrome_ok
    assert np.array_equal(result.certified_user_bits, user)


def test_syndrome_valid_stale_crc_is_refused_once(monkeypatch):
    rng = np.random.default_rng(2209)
    user = rng.integers(0, 2, CMY7_BANK.user_bits, dtype=np.uint8)
    wrong_user = user.copy()
    wrong_user[0] ^= 1
    raw = np.concatenate((wrong_user, crc32_bits(user)))
    transmitted = _encode_raw_frame(raw)

    calls = 0

    def watched_crc(bits):
        nonlocal calls
        calls += 1
        return crc32_bits(bits)

    monkeypatch.setattr(frame, "crc32_bits", watched_crc)
    result = frame.decode_frame(_clean_llrs(transmitted), CMY7_BANK)

    assert all(child.syndrome_ok for child in result.children)
    assert result.crc_invoked and result.crc_ok is False
    assert result.certified_user_bits is None
    assert calls == 1


def test_frame_rejects_malformed_contracts_and_inputs():
    with pytest.raises(ValueError, match="unknown LDPC"):
        frame.FecChildProfile("not-a-code")
    with pytest.raises(ValueError, match=r"\[0, 2240\)"):
        frame.FecChildProfile("r0550", 2240)
    with pytest.raises(ValueError, match="at least one"):
        frame.FecBankProfile("empty", ())
    with pytest.raises(ValueError, match="exactly 5974"):
        frame.encode_frame(np.zeros(3, dtype=np.uint8), CMY7_BANK)
    with pytest.raises(ValueError, match="only 0 or 1"):
        bad = np.zeros(CMY7_BANK.user_bits, dtype=np.uint8)
        bad[0] = 2
        frame.encode_frame(bad, CMY7_BANK)
    with pytest.raises(ValueError, match="only 0 or 1"):
        bad_fractional = np.zeros(CMY7_BANK.user_bits)
        bad_fractional[0] = 0.5
        frame.encode_frame(bad_fractional, CMY7_BANK)
    with pytest.raises(ValueError, match="exactly 10934"):
        frame.decode_frame(np.zeros(3), CMY7_BANK)
    with pytest.raises(ValueError, match="NaN"):
        bad_llrs = np.zeros(CMY7_BANK.transmitted_bits)
        bad_llrs[0] = np.nan
        frame.decode_frame(bad_llrs, CMY7_BANK)
    with pytest.raises(ValueError, match="real numeric"):
        frame.decode_frame(
            np.zeros(CMY7_BANK.transmitted_bits, dtype=np.complex128),
            CMY7_BANK,
        )
    with pytest.raises(ValueError, match=">= 0"):
        frame.decode_frame(
            np.zeros(CMY7_BANK.transmitted_bits), CMY7_BANK, max_iters=-1)


def test_crc_width_remains_the_existing_32_bits():
    assert CRC_BITS == 32

"""The carried tile chain, self-contained: printed cells -> certificate.

Internal (holo2 only). Parity with ``src/holo`` is pinned outside in
``tests/holo2_oracles/test_oracle_tiles.py``; what is checked here is the chain's
own contract — that the field it re-encodes is the field it decodes, that
the CRC gate is what mints a certificate, and that the refusals are
refusals rather than a decoder allowed to guess.

No RNG: the "payload" is a fixed arithmetic bit pattern (DESIGN L11 — a
receiver path with an unseeded draw is a bug, and a test that needs one is
usually testing the draw).
"""
from __future__ import annotations

import numpy as np
import pytest

from holo2.solve import tiles
from holo2.core.records import BlobRef
from holo2.solve import MintRef
from holo2.solve.tiles import AttemptStage, AttemptState, attempt_k_tile
from holo2.format.format_v1 import tile_format

L = 5.0                     # the ideal per-cell magnitude of a clean read


def user_bits_for(fmt, salt: int) -> np.ndarray:
    """A deterministic, balanced user frame (metadata bit first)."""
    index = np.arange(fmt.tile_user_bits, dtype=np.int64)
    return (((index * 2654435761 + salt * 40503) >> 7) & 1).astype(np.uint8)


def printed_field(fmt, page: int, ty: int, tx: int,
                  bits: np.ndarray) -> np.ndarray:
    counter = fmt.tile_counter(page, ty, tx)
    a_t, b_t = tiles._slot_permutation(
        fmt.seed, counter, fmt.n_transmitted_slots)
    return tiles._reencode_printed_cells(
        fmt, counter, page, ty, tx, bits, a_t, b_t)


def llrs(field: np.ndarray, flip_cells: np.ndarray | None = None,
         erase_cells: np.ndarray | None = None) -> np.ndarray:
    out = (field.astype(np.float64) * 2.0 - 1.0) * L
    flat = out.reshape(-1)
    if flip_cells is not None:
        flat[flip_cells] = -flat[flip_cells]
    if erase_cells is not None:
        flat[erase_cells] = 0.0
    return out


#: v2 coding ids (C4, RULINGS G5, 2026-08-22): this file wants SOME
#: row at each of the three K codings, on a grid of its own choosing,
#: so it names the v2 lattice points rather than printed identities.
CODINGS = ("c3-k-r0550", "c2-k-r0550", "c2-k-r0700")


@pytest.mark.parametrize("coding_id", CODINGS)
def test_clean_round_trip_certifies_the_exact_bits(coding_id: str) -> None:
    fmt = tile_format(coding_id, (4, 5))
    for page, ty, tx in ((0, 0, 0), (0, 2, 3), (1, 3, 4)):
        bits = user_bits_for(fmt, ty * 5 + tx + page)
        field = printed_field(fmt, page, ty, tx, bits)
        attempt = attempt_k_tile(llrs(field), fmt, (page, ty, tx),
                                 AttemptStage.SCAN)
        assert attempt.state is AttemptState.CERTIFIED
        assert attempt.certified and attempt.syndrome_ok and attempt.crc_ok
        assert attempt.counter == fmt.tile_counter(page, ty, tx)
        assert attempt.stream_id == "main"
        assert np.array_equal(attempt.user_bits, bits)
        assert attempt.metadata_bit == int(bits[0])
        assert np.array_equal(attempt.symbol_bits, bits[1:])
        # and the certified field is the field that was printed
        assert np.array_equal(tiles.printed_cells(fmt, attempt), field)


def test_decoder_profile_names_the_executed_decoder() -> None:
    fmt = tile_format("c2-k-r0700", (2, 2))
    field = printed_field(fmt, 0, 0, 0, user_bits_for(fmt, 1))
    scan = attempt_k_tile(llrs(field), fmt, (0, 0, 0), AttemptStage.SCAN)
    retry = attempt_k_tile(llrs(field), fmt, (0, 0, 0),
                           AttemptStage.RETRY150)
    assert scan.decoder_profile == "r0700/decode_tile-max60-alpha0.8"
    assert retry.decoder_profile == "r0700/decode_tile-max150-alpha0.8"


def test_the_chain_corrects_errors_then_refuses(monkeypatch) -> None:
    """Few flips certify; many flips refuse — and never half-certify."""
    fmt = tile_format("c3-k-r0550", (2, 2))
    bits = user_bits_for(fmt, 11)
    field = printed_field(fmt, 0, 1, 1, bits)
    outcomes = []
    for n_flips in (0, 40, 400, 1600):
        flips = (np.arange(n_flips, dtype=np.int64) * 2411) % 4096
        flips = np.unique(flips)
        attempt = attempt_k_tile(llrs(field, flip_cells=flips), fmt,
                                 (0, 1, 1), AttemptStage.SCAN)
        outcomes.append(attempt.state)
        if attempt.certified:
            assert np.array_equal(attempt.user_bits, bits)
        else:
            assert attempt.user_bits is None       # never uncertified bits
            assert attempt.metadata_bit is None
    assert outcomes[0] is AttemptState.CERTIFIED
    assert outcomes[-1] is AttemptState.ATTEMPTED_FAILED


def test_erasures_below_the_counting_bound_never_reach_the_decoder() -> None:
    """k_eff is a counting bound: fewer live cells than unknowns cannot
    determine the codeword under ANY decoder, so the attempt stops."""
    fmt = tile_format("c2-k-r0700", (2, 2))
    field = printed_field(fmt, 0, 0, 1, user_bits_for(fmt, 3))
    k_eff = tiles.k_eff_bits(fmt)
    assert k_eff == 2880 - 100
    # site cells never count as informative, so the floor is counted over
    # the payload cells alone: leave exactly one fewer live than unknowns.
    nonsite = np.flatnonzero(~tiles._geometry(fmt).site_mask_yx.reshape(-1))
    attempt = attempt_k_tile(llrs(field, erase_cells=nonsite[k_eff - 1:]),
                             fmt, (0, 0, 1), AttemptStage.SCAN)
    assert attempt.state is AttemptState.BELOW_ATTEMPT_FLOOR
    assert attempt.n_informative == k_eff - 1
    assert attempt.n_iters == 0
    assert attempt.syndrome_ok is None and attempt.crc_ok is None
    # one more live cell and the decoder is allowed to try
    allowed = attempt_k_tile(llrs(field, erase_cells=nonsite[k_eff:]),
                             fmt, (0, 0, 1), AttemptStage.SCAN)
    assert allowed.n_informative == k_eff
    assert allowed.state is not AttemptState.BELOW_ATTEMPT_FLOOR


def test_site_cells_are_erased_not_read() -> None:
    """Word/filler sites are known values, never payload evidence."""
    fmt = tile_format("c3-k-r0550", (2, 2))
    bits = user_bits_for(fmt, 5)
    field = printed_field(fmt, 0, 0, 0, bits)
    sites = tiles._geometry(fmt).site_flat
    poisoned = llrs(field)
    poisoned.reshape(-1)[sites] = -1e3 * L      # nonsense at every site
    attempt = attempt_k_tile(poisoned, fmt, (0, 0, 0), AttemptStage.SCAN)
    assert attempt.certified and np.array_equal(attempt.user_bits, bits)


def test_non_finite_llrs_are_a_detector_fault() -> None:
    fmt = tile_format("c2-k-r0550", (2, 2))
    field = printed_field(fmt, 0, 0, 0, user_bits_for(fmt, 7))
    for bad in (np.inf, -np.inf, np.nan):
        broken = llrs(field)
        broken[3, 4] = bad
        with pytest.raises(ValueError, match="finite"):
            attempt_k_tile(broken, fmt, (0, 0, 0), AttemptStage.SCAN)
    with pytest.raises(ValueError, match=r"must be \(64, 64\)"):
        attempt_k_tile(np.zeros((64, 63)), fmt, (0, 0, 0), AttemptStage.SCAN)


def test_an_address_outside_the_page_is_refused() -> None:
    fmt = tile_format("c2-k-r0550", (2, 2))
    field = printed_field(fmt, 0, 0, 0, user_bits_for(fmt, 9))
    with pytest.raises(ValueError, match="outside grid"):
        attempt_k_tile(llrs(field), fmt, (0, 2, 0), AttemptStage.SCAN)


def test_a_wrong_geometry_hypothesis_decodes_to_nothing() -> None:
    """The seed embeds the cell field, so the wrong grid descrambles to
    coin flips — HOLO-DESIGN §4.5, the reason dimensions are part of the
    printed identity and not a convenience."""
    printed = tile_format("c2-k-r0700", (53, 37))
    guessed = tile_format("c2-k-r0700", (52, 36))
    assert printed.seed != guessed.seed
    field = printed_field(printed, 0, 3, 4, user_bits_for(printed, 2))
    attempt = attempt_k_tile(llrs(field), guessed, (0, 3, 4),
                             AttemptStage.SCAN)
    assert attempt.state is AttemptState.ATTEMPTED_FAILED


# --------------------------------------------------------- record boundary

def test_certified_tile_record_is_the_5_2_record() -> None:
    fmt = tile_format("c3-k-r0550", (2, 2))
    bits = user_bits_for(fmt, 13)
    field = printed_field(fmt, 0, 0, 0, bits)
    attempt = attempt_k_tile(llrs(field), fmt, (0, 0, 0), AttemptStage.SCAN)
    ref = BlobRef("ab" * 32, attempt.symbol_bits.size, dtype="|u1",
                  shape=(attempt.symbol_bits.size,))
    minting = MintRef("pose-1", "scan", "fixture-decoder")
    record = tiles.certified_tile_record(
        attempt, minting=minting, bits_ref=ref,
        observed_by=("cap:8/1", "cap:2/1", "cap:8/1"))
    assert record.certified
    assert record.minting == minting and record.bits_ref == ref
    assert record.metadata_bit == int(bits[0])
    assert record.observed_by == ("cap:2/1", "cap:8/1")   # sorted unique


def test_an_uncertified_attempt_has_no_record() -> None:
    fmt = tile_format("c3-k-r0550", (2, 2))
    attempt = attempt_k_tile(np.zeros((64, 64)), fmt, (0, 0, 0),
                             AttemptStage.SCAN)
    assert attempt.state is AttemptState.BELOW_ATTEMPT_FLOOR
    with pytest.raises(ValueError, match="not a certificate"):
        tiles.certified_tile_record(
            attempt, minting=MintRef("pose-1", "scan", "fixture-decoder"),
            bits_ref=BlobRef("ab" * 32, 1))
    with pytest.raises(ValueError, match="only for a certified tile"):
        tiles.printed_cells(fmt, attempt)

"""Lane-W Stage A, unit by unit: slot geometry, the gates, the trial order.

W0 sub-wave A2 (H4-PLAN §3-W0).  ``solve/words.py`` is a port of v1's
``receive/words.py``, and R4 pins it BEHAVIOURALLY — so every number here is
hand-derived from the published rule and written as a literal with its
derivation in a comment, never "whatever the code returns".  Importing
``holo`` to cross-check would violate the firewall; the cross-tree
differential is W0-B's.

The arithmetic under test, once:

* a full slot needs 64 cells, so an extent of ``E`` holds
  ``(E - 64) // 64 + 1`` of them, and a patch narrower than 64 holds none;
* every slot is DECLARED at the base slot's fitting-phase room,
  ``min(64, H-63) * min(64, W-63)``, which over-declares the trailing
  row/column on purpose (the union bound needs the declaration to dominate
  the attempts, never to equal them);
* the declared Stage-A domain sums that over four ``rot90`` orientations;
* candidates come back sorted by ``(errors, slot_index, rot_k, phase_index)``.

Decode fixtures are 64x192 strips: three slots in a row, all four
orientations live, 4 x 3 x 64 = 768 declared hypotheses — about 500 real BCH
decodes, which is two orders of magnitude cheaper than the 200x200 E022
window (75,076) and exercises exactly the same sweep.
"""
from __future__ import annotations

import numpy as np
import pytest

from holo2.format import bch, pilots
from holo2.format.format_v1 import TileFormat
from holo2.solve import words
from holo2.solve.place_model import WordAttemptBudget
from holo2.format.format_v1 import tile_format

# The 8x8 grid the other solve unit tests use: 64 tiles/page, and
# 2**18 / 64 = 4096 pages exactly, so no counter is out of the page domain.
SPEC = tile_format("c2-k-r0550", (8, 8))
# A row at the A4/6 mm tile matrix, 52x36 = 1872 tiles a page, which is
# what this fixture is FOR: 2**18 = 262144 = 1872 * 140 + 64, so
# max_pages is 140 and the last 64 counters address a page the row does
# not have.  A v2 row since C4 (RULINGS G5, 2026-08-22) — the counter
# arithmetic is a property of the tile matrix and not of a namespace, and
# the PRINTED A4 identity is ``L:c2-r0700@3328x2304``, which
# ``test_format_rows`` names where it matters.
A4_SPEC = tile_format("c2-k-r0700", (52, 36))

STRIP = (64, 192)                       # 3 slots in a row; 768 hypotheses
STRIP_BUDGET = WordAttemptBudget(768, 1e-3, "test/words-kernel-strip")
TILE_BUDGET = WordAttemptBudget(4, 1e-3, "test/words-kernel-tile")


# ------------------------------------------------------------- the fixtures

def _printed_word(spec: TileFormat, counter: int, *,
                  flips: tuple[int, ...] = (),
                  pad: tuple[int, ...] = ()) -> np.ndarray:
    """The 100 printed values of one tile's word: BCH(message) XOR scramble.

    Built through ``holo2.format.bch`` rather than through the pilots
    convenience wrapper, so the test states the whole chain Stage A inverts:
    18 counter bits MSB-first, 5 pads (zero unless ``pad`` names one), encode,
    scramble, then optionally flip channel errors into the printed values.
    """
    message = np.zeros(pilots.MESSAGE_BITS, np.uint8)
    for index in range(pilots.COUNTER_BITS):
        message[index] = (counter >> (pilots.COUNTER_BITS - 1 - index)) & 1
    for index in pad:
        message[pilots.COUNTER_BITS + index] = 1
    scramble = pilots.value_scramble_bits(spec.seed, spec.plane)
    values = (bch.encode(message) ^ scramble).copy()
    for site in flips:
        values[site] ^= 1
    return values


def _sites(spec: TileFormat) -> np.ndarray:
    return pilots.word_site_cells_yx(spec.family_seed)


def _plant(grid: np.ndarray, spec: TileFormat, values: np.ndarray, *,
           rot_k: int = 0, origin: tuple[int, int] = (0, 0)) -> np.ndarray:
    """Write one word so it reads at ``origin`` of the ``rot_k`` orientation.

    ``np.rot90`` returns a VIEW, so writing through the oriented frame lands
    the values in the base grid exactly where that orientation will gather
    them — which is how a rot1 seed is planted without rotating the fixture.
    Returns the base-grid cells written, so a mask test can hide them.
    """
    view = np.rot90(grid, rot_k)
    sites = _sites(spec)
    rows = origin[0] + sites[:, 0]
    cols = origin[1] + sites[:, 1]
    view[rows, cols] = values
    written = np.zeros(grid.shape, bool)
    np.rot90(written, rot_k)[rows, cols] = True
    return written


def _strip() -> tuple[np.ndarray, np.ndarray]:
    """A blank 64x192 strip and its all-visible mask."""
    return np.zeros(STRIP, np.uint8), np.ones(STRIP, bool)


# --------------------------------------------------------- the slot grid

def test_the_slot_grid_is_every_full_slot_in_row_major_order() -> None:
    # 200 cells hold (200-64)//64 + 1 = 2 + 1 = 3 slots per axis.
    assert words._slot_grid((200, 200)) == (
        (0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2))
    # Exactly one tile: one slot.  70 cells: (70-64)//64 + 1 = 1, still one.
    assert words._slot_grid((64, 64)) == ((0, 0),)
    assert words._slot_grid((70, 70)) == ((0, 0),)
    # The 64x192 decode strip: 1 x ((192-64)//64 + 1) = 3.
    assert words._slot_grid(STRIP) == ((0, 0), (0, 1), (0, 2))
    # An axis under one tile fits no full slot at all, however long the other.
    assert words._slot_grid((63, 200)) == ()
    assert words._slot_grid((200, 63)) == ()
    # The real A4 rows: 3328/64 = 52 and 2304/64 = 36 slots per axis, so the
    # slot grid of a whole page is its tile grid.
    assert len(words._slot_grid((3328, 2304))) == 52 * 36 == 1872
    assert len(words._slot_grid((2240, 1536))) == 35 * 24 == 840


def test_the_declared_phase_capacity_is_the_base_slots_room() -> None:
    # min(64, 200-63) = min(64, 137) = 64 on both axes.
    assert words._slot_phase_capacity((200, 200)) == 64 * 64 == 4096
    # min(64, 70-63) = 7: the whole-window fitting room when only one slot
    # fits at all.
    assert words._slot_phase_capacity((70, 70)) == 7 * 7 == 49
    assert words._slot_phase_capacity((64, 64)) == 1
    # Rectangular: min(64, 37) x min(64, 17).
    assert words._slot_phase_capacity((100, 80)) == 37 * 17 == 629
    # The strip: one phase row, 64 phase columns.
    assert words._slot_phase_capacity(STRIP) == 1 * 64 == 64
    # No full slot, no phases.
    assert words._slot_phase_capacity((63, 200)) == 0


def test_the_trailing_slot_admits_fewer_phases_than_it_declares() -> None:
    """The over-declaration the union bound is allowed to make."""
    # Base slot: the declared capacity, exactly.
    assert words._slot_phase_shape((200, 200), (0, 0)) == (64, 64)
    # Interior slot: base_y = 64, min(64, 200-64-63) = min(64, 73) = 64.
    assert words._slot_phase_shape((200, 200), (1, 1)) == (64, 64)
    # Trailing slot: base = 128, min(64, 200-128-63) = 9 — so this slot
    # physically admits 81 phases against the 4096 declared for it.
    assert words._slot_phase_shape((200, 200), (2, 2)) == (9, 9)
    assert 9 * 9 < words._slot_phase_capacity((200, 200))
    # The strip's last slot: base_x = 128, min(64, 192-128-63) = 1.
    assert words._slot_phase_shape(STRIP, (0, 2)) == (1, 1)


def test_the_centre_slot_is_nearest_the_patch_centre() -> None:
    # 200x200: slot (r,c) sits at |64r + 64 - 100| + |64c + 64 - 100|;
    # r=0 -> 36, r=1 -> 28, r=2 -> 92, so the middle slot wins with 56.
    assert words._centre_slot((200, 200)) == (1, 1)
    # 128x128: r=0 -> |64-64| = 0, r=1 -> |128-64| = 64.
    assert words._centre_slot((128, 128)) == (0, 0)
    # 192x64: r=0 -> |64-96| = 32 and r=1 -> |128-96| = 32 TIE, broken by
    # the slot itself (the key's second term), so the first slot wins.
    assert words._centre_slot((192, 64)) == (0, 0)
    # The strip: c=0 -> |64-96| = 32 and c=1 -> |128-96| = 32 tie the same way.
    assert words._centre_slot(STRIP) == (0, 0)
    # No full slot, no centre.
    assert words._centre_slot((63, 63)) is None


# ----------------------------------------------------- the declared domain

def test_stage_a_hypotheses_over_the_real_windows_and_rows() -> None:
    # The E022 window pin (words.py:162-164): 9 slots x 64x64 x 4.
    assert words.stage_a_hypotheses((200, 200)) == 9 * 4096 * 4 == 147_456
    # 70x70: one slot, its 7x7 fitting phases, four orientations.
    assert words.stage_a_hypotheses((70, 70)) == 4 * 49 == 196
    # One tile: one slot, one phase, four orientations.
    assert words.stage_a_hypotheses((64, 64)) == 4
    # Oblong: rot0/rot2 see 2x3 slots, rot1/rot3 see 3x2 — six either way,
    # each declared at the full 64x64, so the orientations agree.
    assert words.stage_a_hypotheses((128, 200)) == 6 * 4096 * 4 == 98_304
    # The strip: 3 slots x 64 phases x 4 orientations.
    assert words.stage_a_hypotheses(STRIP) == 3 * 64 * 4 == 768
    # The real A4 rows, as whole-page patches: every slot is interior enough
    # to declare the full 4096, so this is slots x 4096 x 4.
    assert words.stage_a_hypotheses((3328, 2304)) == 1872 * 4096 * 4
    assert words.stage_a_hypotheses((3328, 2304)) == 30_670_848
    assert words.stage_a_hypotheses((2240, 1536)) == 840 * 4096 * 4
    assert words.stage_a_hypotheses((2240, 1536)) == 13_762_560
    # No full slot: an empty domain, not a refusal.
    assert words.stage_a_hypotheses((63, 200)) == 0


def test_stage_a_hypotheses_refuses_anything_but_two_cell_counts() -> None:
    assert words.stage_a_hypotheses(np.zeros(STRIP, np.uint8).shape) == 768
    for bad in ((200,), (200, 200, 3), (-1, 200), (200, -1)):
        with pytest.raises(ValueError, match="two nonnegative integers"):
            words.stage_a_hypotheses(bad)
    for not_a_count in (True, 1.0, "64", None):
        with pytest.raises(ValueError, match="two nonnegative integers"):
            words.stage_a_hypotheses((not_a_count, 64))  # type: ignore[arg-type]
    # numpy integers are counts; numpy booleans are not.
    assert words.stage_a_hypotheses((np.int64(64), np.int32(64))) == 4
    with pytest.raises(ValueError, match="two nonnegative integers"):
        words.stage_a_hypotheses((np.bool_(True), 64))  # type: ignore[arg-type]


# --------------------------------------------------------------- the gather

def test_the_gather_enumerates_phases_row_major_and_samples_them() -> None:
    """The phase enumeration the sort key's last term indexes."""
    grid = np.arange(64 * 192, dtype=np.uint8).reshape(STRIP)
    mask = np.ones(STRIP, bool)
    positions = _sites(SPEC)
    gathered = words._gather_slot(grid, mask, STRIP, (0, 1), positions)
    assert gathered is not None
    # Slot (0,1) admits 1 phase row x 64 phase columns.
    assert gathered.words.shape == (64, pilots.N_WORD_SITES)
    assert gathered.origins_y.tolist() == [0] * 64
    assert gathered.origins_x.tolist() == list(range(64, 128))
    for phase in (0, 1, 63):
        origin = (int(gathered.origins_y[phase]),
                  int(gathered.origins_x[phase]))
        expected = grid[origin[0] + positions[:, 0],
                        origin[1] + positions[:, 1]]
        assert np.array_equal(gathered.words[phase], expected)
    # A slot with no fitting phase is skipped, not returned empty.
    assert words._gather_slot(grid, mask, STRIP, (0, 3), positions) is None


# ------------------------------------------------------ decode: the chain

def test_a_real_code_word_decodes_to_its_own_tile_address() -> None:
    """Real code word in, candidate out: the whole Stage-A chain."""
    # page 3, tile (5,6) of an 8x8 grid: 3*64 + 5*8 + 6 = 238.
    counter = SPEC.tile_counter(3, 5, 6)
    assert counter == 238
    grid, mask = _strip()
    _plant(grid, SPEC, _printed_word(SPEC, counter), origin=(0, 64))

    result = words.stage_a(grid, mask, SPEC, STRIP_BUDGET)

    assert result.reason == "candidates"
    assert result.hypotheses == 768
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.counter == counter
    assert candidate.page == 3
    assert candidate.tile_yx == (5, 6)
    assert candidate.errors == 0
    assert candidate.rot_k == 0
    assert candidate.oriented_origin_yx == (0, 64)
    # page_origin = tile*64 - origin = (5*64 - 0, 6*64 - 64).
    assert candidate.page_origin_yx == (320, 320)


def test_a_blank_field_declares_its_domain_and_finds_nothing() -> None:
    grid, mask = _strip()
    result = words.stage_a(grid, mask, SPEC, STRIP_BUDGET)
    assert result.candidates == ()
    assert result.hypotheses == 768
    assert result.reason == "no_word_candidate"


def test_errors_are_corrected_to_the_bound_and_no_further() -> None:
    """t=13 is the radius; 14 flips leave the printed counter unreachable."""
    at_bound = SPEC.tile_counter(0, 1, 1)
    over_bound = SPEC.tile_counter(0, 2, 2)
    grid, mask = _strip()
    _plant(grid, SPEC, _printed_word(SPEC, at_bound, flips=tuple(range(13))),
           origin=(0, 0))
    _plant(grid, SPEC, _printed_word(SPEC, over_bound, flips=tuple(range(14))),
           origin=(0, 64))

    result = words.stage_a(grid, mask, SPEC, STRIP_BUDGET)

    assert [(c.counter, c.errors) for c in result.candidates] == [
        (at_bound, 13)]
    assert over_bound not in [c.counter for c in result.candidates]


def test_the_visibility_floor_is_a_strict_per_phase_site_count() -> None:
    """90 visible sites pass, 89 do not — and the floor is per phase."""
    assert words.STAGE_A_MIN_VISIBLE_SITES == 90
    visible_90 = SPEC.tile_counter(0, 1, 1)
    visible_89 = SPEC.tile_counter(0, 2, 2)
    grid, mask = _strip()
    kept = _plant(grid, SPEC, _printed_word(SPEC, visible_90), origin=(0, 0))
    dropped = _plant(grid, SPEC, _printed_word(SPEC, visible_89),
                     origin=(0, 64))
    mask[np.nonzero(kept)[0][:10], np.nonzero(kept)[1][:10]] = False
    mask[np.nonzero(dropped)[0][:11], np.nonzero(dropped)[1][:11]] = False

    result = words.stage_a(grid, mask, SPEC, STRIP_BUDGET)

    assert [c.counter for c in result.candidates] == [visible_90]


def test_the_pad_and_page_domain_gates_refuse_illegal_words() -> None:
    """Two refusals a decodable code word can still earn."""
    legal = A4_SPEC.tile_counter(6, 0, 0)
    # 2**18 - 1 = 262143 -> page 140, and this row has pages 0..139.
    off_page = 262_143
    assert A4_SPEC.max_pages == 140
    assert A4_SPEC.tile_address(off_page)[0] == 140
    grid, mask = _strip()
    _plant(grid, A4_SPEC, _printed_word(A4_SPEC, legal), origin=(0, 0))
    _plant(grid, A4_SPEC, _printed_word(A4_SPEC, off_page), origin=(0, 64))
    # A perfectly decodable code word whose known-zero pads are not zero.
    _plant(grid, A4_SPEC, _printed_word(A4_SPEC, legal, pad=(2,)),
           origin=(0, 128))

    result = words.stage_a(grid, mask, A4_SPEC, STRIP_BUDGET)

    assert [(c.counter, c.oriented_origin_yx) for c in result.candidates] == [
        (legal, (0, 0))]


# ---------------------------------------------------------- the trial order

def test_candidates_are_errors_first_then_slot_then_orientation() -> None:
    """The global sort key, with a rot1 seed beating a nearer rot0 one."""
    five_errors = SPEC.tile_counter(0, 0, 0)
    clean_slot1 = SPEC.tile_counter(0, 3, 3)
    clean_rot1 = SPEC.tile_counter(0, 5, 5)
    grid, mask = _strip()
    _plant(grid, SPEC, _printed_word(SPEC, five_errors,
                                     flips=(3, 17, 42, 68, 91)),
           origin=(0, 0))
    _plant(grid, SPEC, _printed_word(SPEC, clean_slot1), origin=(0, 64))
    # rot1's slot (0,0) covers base-grid rows 0..63, columns 128..191 — the
    # strip's third slot, so the three plants never overlap.
    _plant(grid, SPEC, _printed_word(SPEC, clean_rot1), rot_k=1, origin=(0, 0))

    result = words.stage_a(grid, mask, SPEC, STRIP_BUDGET)

    # Keys: rot1 slot0 (0,0,1,0) < rot0 slot1 (0,1,0,0) < rot0 slot0 (5,0,0,0).
    # Errors first (the five-error seed is last despite sitting in slot 0),
    # then the oriented row-major slot index (which puts the rot1 seed ahead
    # of the clean rot0 one), and rot_k only after that.
    assert [(c.counter, c.rot_k, c.errors) for c in result.candidates] == [
        (clean_rot1, 1, 0), (clean_slot1, 0, 0), (five_errors, 0, 5)]


def test_equal_error_equal_slot_candidates_break_by_rot_k() -> None:
    """The tie the previous test cannot show: same errors, same slot index."""
    rot0 = SPEC.tile_counter(0, 1, 2)
    rot1 = SPEC.tile_counter(0, 4, 4)
    grid, mask = _strip()
    _plant(grid, SPEC, _printed_word(SPEC, rot0), origin=(0, 0))
    _plant(grid, SPEC, _printed_word(SPEC, rot1), rot_k=1, origin=(0, 0))

    result = words.stage_a(grid, mask, SPEC, STRIP_BUDGET)

    # Both keys are (0, 0, rot_k, 0): identical but for the orientation.
    assert [(c.counter, c.rot_k) for c in result.candidates] == [
        (rot0, 0), (rot1, 1)]


# ------------------------------------------------------------- the staging

def test_centre_and_rest_partition_the_all_slot_sweep() -> None:
    """v0.26's two spends cover the sweep exactly once between them."""
    grid, mask = _strip()
    counters = [SPEC.tile_counter(0, 0, index) for index in range(3)]
    for index, counter in enumerate(counters):
        _plant(grid, SPEC, _printed_word(SPEC, counter),
               origin=(0, 64 * index))

    everything = words.stage_a(grid, mask, SPEC, STRIP_BUDGET, slots="all")
    centre = words.stage_a(grid, mask, SPEC, STRIP_BUDGET, slots="centre")
    rest = words.stage_a(grid, mask, SPEC, STRIP_BUDGET, slots="rest")

    # The declared domain is the full multi-slot ceiling in every stage —
    # a stage that decodes fewer slots under the same declaration is
    # conservative, never a different budget.
    assert centre.hypotheses == rest.hypotheses == everything.hypotheses == 768
    # The strip's centre slot is (0,0) (the tie above), so the centre stage
    # reads the first tile and the rest stage reads the other two.
    assert [c.counter for c in centre.candidates] == [counters[0]]
    assert [c.counter for c in rest.candidates] == counters[1:]
    assert [c.counter for c in everything.candidates] == counters
    assert (set(map(repr, centre.candidates))
            | set(map(repr, rest.candidates))
            == set(map(repr, everything.candidates)))
    assert not (set(map(repr, centre.candidates))
                & set(map(repr, rest.candidates)))


def test_an_unknown_slot_stage_is_refused() -> None:
    grid = np.zeros((64, 64), np.uint8)
    mask = np.ones((64, 64), bool)
    with pytest.raises(ValueError, match="all, centre, or rest"):
        words.stage_a(grid, mask, SPEC, TILE_BUDGET,
                      slots="bogus")  # type: ignore[arg-type]


# ------------------------------------------------------- refusals and seams

def test_a_domain_over_the_declared_budget_refuses_the_whole_stage() -> None:
    grid, mask = _strip()
    _plant(grid, SPEC, _printed_word(SPEC, SPEC.tile_counter(0, 0, 0)))
    short = WordAttemptBudget(767, 1e-3, "test/one-short")

    result = words.stage_a(grid, mask, SPEC, short)

    # The declared domain is still reported — the refusal is auditable.
    assert result == words.StageAResult((), 768, "attempt_budget_exceeded")


def test_bits_and_mask_must_be_equal_two_dimensional_fields() -> None:
    for bits, mask in (
        (np.zeros((64, 64, 3), np.uint8), np.ones((64, 64, 3), bool)),
        (np.zeros(64, np.uint8), np.ones(64, bool)),
        (np.zeros((64, 64), np.uint8), np.ones((64, 65), bool)),
    ):
        with pytest.raises(ValueError, match="equal 2-D arrays"):
            words.stage_a(bits, mask, SPEC, TILE_BUDGET)


def test_stage_a_patch_reads_bits_and_mask_off_the_protocol() -> None:
    """The AddressPatchLike seam W0-B reconciles with pose_fit.AddressPatch."""

    class _Patch:
        def __init__(self, bits: np.ndarray, mask: np.ndarray) -> None:
            self.bits = bits
            self.mask = mask

    counter = SPEC.tile_counter(1, 7, 7)
    grid = np.zeros((64, 64), np.uint8)
    _plant(grid, SPEC, _printed_word(SPEC, counter))
    patch: words.AddressPatchLike = _Patch(grid, np.ones((64, 64), bool))

    result = words.stage_a_patch(patch, SPEC, TILE_BUDGET)

    assert [(c.counter, c.rot_k) for c in result.candidates] == [(counter, 0)]
    assert result.hypotheses == 4
    assert result == words.stage_a(grid, patch.mask, SPEC, TILE_BUDGET)


# --------------------------------------------------- the two decoder arms

def test_the_batched_word_sweep_is_the_same_stage_a(
) -> None:
    """``batched_sweep`` picks an ARM, never an answer — the wiring pin.

    The equivalence PROOF is ``holo2/measure/bch_equivalence.py`` (two
    populations, run by path, never collected).  This is the cheap guard
    that keeps the twin alive while the switch defaults OFF: it plants a
    strip that exercises every branch of ``bch_batch``'s five rules — a
    clean codeword (all-zero syndrome), a word at the correction bound
    (BM + Chien + the re-check all succeed), one past it (refused), a
    rotated seed, and ~500 blank-field decodes that refuse at every stage
    — and asserts the two arms agree candidate for candidate, in order.
    """
    grid, mask = _strip()
    _plant(grid, SPEC, _printed_word(SPEC, SPEC.tile_counter(0, 0, 0)),
           origin=(0, 0))
    _plant(grid, SPEC, _printed_word(SPEC, SPEC.tile_counter(1, 1, 1),
                                     flips=tuple(range(13))), origin=(0, 64))
    _plant(grid, SPEC, _printed_word(SPEC, SPEC.tile_counter(2, 2, 2),
                                     flips=tuple(range(14))), origin=(0, 128))
    _plant(grid, SPEC, _printed_word(SPEC, SPEC.tile_counter(3, 3, 3)),
           rot_k=1, origin=(0, 0))

    oracle = words.stage_a(grid, mask, SPEC, STRIP_BUDGET)
    twin = words.stage_a(grid, mask, SPEC, STRIP_BUDGET, batched_sweep=True)

    # Not merely equal counts: the whole frozen result, order included.
    assert twin == oracle
    assert len(oracle.candidates) >= 3          # the fixture really decoded

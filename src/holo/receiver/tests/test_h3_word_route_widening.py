"""Multi-slot Stage A widening (PLACEMENT-IMPROVEMENTS 3.1-3.3).

Moved here from tests/holo/test_word_route_widening.py on 2026-09-20:
the Gate E re-home left it reading `holo.receiver` alone, so it was a
receiver test sitting in the generator lane, paying 3.8 s of it.

Gate E re-home: the vehicle is `holo.receiver.plugins.words` — the production
word route, which carries the same complete-slot-grid sweep, the same
per-slot visibility floor and the same one global errors-first order.
Two of the six pins were v1-receiver policy objects and did not survive;
the format fact under them (the single-word union-bound term) is pinned
in test_h3_plugins_placement.py.
"""
from __future__ import annotations

import numpy as np

from holo.receiver.format import pilots
from holo.receiver.format.identity import resolve_format_ref
from holo.receiver.plugins import words

ROW = resolve_format_ref("c3-k-r0550@7x7")
PLANE = words.addressing_plane(ROW)


def _paint_word(
    grid: np.ndarray,
    counter: int,
    origin_yx: tuple[int, int],
    *,
    flip_sites: tuple[int, ...] = (),
) -> None:
    """Render one tile's printed word bits at ``origin_yx`` of ``grid``."""
    positions = pilots.word_site_cells_yx(ROW.sites_seed)
    values = pilots.word_values(ROW.seed, counter, PLANE)[0].copy()
    for site in flip_sites:
        values[site] ^= 1
    grid[
        origin_yx[0] + positions[:, 0], origin_yx[1] + positions[:, 1]
    ] = values


def test_stage_a_hypotheses_declares_the_complete_slot_grid() -> None:
    # 200x200: 9 slots x (64x64 declared phases) x 4 orientations.
    assert words.stage_a_hypotheses((200, 200)) == 9 * 4096 * 4 == 147_456
    # 128x200: 6 slots per orientation (2x3 rot0/rot2, 3x2 rot1/rot3),
    # each declared at 64x64 phases: 4 x 6 x 4096.
    assert words.stage_a_hypotheses((128, 200)) == 6 * 4096 * 4 == 98_304
    # 70x70: one slot, 7x7 fitting phases, 4 orientations.
    assert words.stage_a_hypotheses((70, 70)) == 196
    # 64x64: one slot, one phase, 4 orientations.
    assert words.stage_a_hypotheses((64, 64)) == 4
    # No full slot fits: empty domain.
    assert words.stage_a_hypotheses((63, 200)) == 0


def test_multi_slot_sweep_decodes_away_from_a_masked_centre() -> None:
    rng = np.random.default_rng(20260731)
    bits = rng.integers(0, 2, (200, 200), dtype=np.uint8)
    # Real reference words for the 3x3 fully contained tile grid of an
    # origin-aligned 200-cell window on page 0.
    for tile_y in range(3):
        for tile_x in range(3):
            _paint_word(
                bits,
                ROW.tile_counter(0, tile_y, tile_x),
                (64 * tile_y, 64 * tile_x),
            )
    mask = np.ones((200, 200), dtype=bool)
    mask[64:128, 64:128] = False    # the historically selected centre slot

    result = words.stage_a(bits, mask, ROW)

    assert result.reason == "candidates"
    assert result.hypotheses == 147_456
    tiles = [candidate.tile_yx for candidate in result.candidates]
    # Every visible slot decodes its own tile; the masked centre slot is
    # refused by the per-phase >=90/100 visibility floor, and no
    # window-wide mask gate exists to refuse the whole route (mean mask
    # here is 0.90 > the removed 0.82 threshold, but a fully masked slot
    # plus e.g. margins would previously have killed pristine corners).
    assert (1, 1) not in tiles
    assert tiles == [
        (0, 0), (0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1), (2, 2),
    ]
    for candidate in result.candidates:
        assert candidate.errors == 0
        assert candidate.rot_k == 0
        assert candidate.page == 0
        assert candidate.page_origin_yx == (0, 0)
        assert candidate.oriented_origin_yx == (
            64 * candidate.tile_yx[0], 64 * candidate.tile_yx[1])


def test_candidates_are_globally_errors_first_across_orientations() -> None:
    rng = np.random.default_rng(20260732)
    bits = rng.integers(0, 2, (200, 200), dtype=np.uint8)
    # rot0 seed with five word-site errors in slot (0, 0).
    _paint_word(
        bits, ROW.tile_counter(0, 0, 0), (0, 0),
        flip_sites=(3, 17, 42, 68, 91),
    )
    # Clean rot1 seed: paint into the rot1-oriented frame at slot (2, 2)
    # and rotate back (the two painted regions are disjoint).
    oriented = np.rot90(bits, 1).copy()
    _paint_word(oriented, ROW.tile_counter(0, 5, 5), (128, 128))
    bits = np.ascontiguousarray(np.rot90(oriented, -1))
    mask = np.ones((200, 200), dtype=bool)

    result = words.stage_a(bits, mask, ROW)

    # The historical per-orientation concatenation would have tried the
    # five-error rot0 seed first; the global sort tries the clean rot1
    # seed first.  Ties would break by (slot row-major index, rot_k,
    # phase enumeration) — here the error counts already order the trial.
    assert [
        (candidate.rot_k, candidate.errors)
        for candidate in result.candidates
    ] == [(1, 0), (0, 5)]
    assert result.candidates[0].tile_yx == (5, 5)
    assert result.candidates[1].tile_yx == (0, 0)


def test_staged_slot_stages_partition_the_sweep() -> None:
    """Centre + rest partition exactly the all-slot candidate set."""
    rng = np.random.default_rng(20260731)
    bits = rng.integers(0, 2, (200, 200), dtype=np.uint8)
    for tile_y in range(3):
        for tile_x in range(3):
            _paint_word(
                bits,
                ROW.tile_counter(0, tile_y, tile_x),
                (64 * tile_y, 64 * tile_x),
            )
    mask = np.ones((200, 200), dtype=bool)
    everything = words.stage_a(bits, mask, ROW, words.STAGE_ALL)
    centre = words.stage_a(bits, mask, ROW, words.STAGE_CENTRE)
    rest = words.stage_a(bits, mask, ROW, words.STAGE_REST)
    assert centre.hypotheses == everything.hypotheses == 147_456
    assert centre.candidates, "centre stage must decode the interior slot"
    union = set(map(repr, centre.candidates)) | set(map(repr, rest.candidates))
    assert union == set(map(repr, everything.candidates))
    assert not (set(map(repr, centre.candidates))
                & set(map(repr, rest.candidates)))
    # v1 refused an unknown stage name; holo3 falls through to the full
    # sweep instead, so the refusal pin has no holo3 counterpart to keep.
    # A typo costs the all-slot price, never a wrong answer.

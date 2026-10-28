"""receive/words: multi-slot Stage A widening (PLACEMENT-IMPROVEMENTS 3.1-3.3).

Covers the three coherent word-route amendments: the complete-slot-grid
Stage-A domain and its declared hypothesis arithmetic, per-slot (visibility
floor) protection replacing the removed window-wide mask gate, and the
global errors-first candidate ordering across slots and orientations.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from holo.devices.profiles import make_spec
from holo.format import pilots
from holo.format.registry import registered_format_rows
from holo.receive.placement.defaults import PROVISIONAL_V1_PLACEMENT_POLICY
from holo.receive.placement.model import PlacementConfig
from holo.receive.placement.policy import PlacementDomainEnvelope
from holo.receive.words import WordAttemptBudget, stage_a, stage_a_hypotheses


SPEC = make_spec("c3-r0550")
WINDOW_BUDGET = WordAttemptBudget(147_456, 1e-3, "test/word-route-widening")


def _paint_word(
    grid: np.ndarray,
    counter: int,
    origin_yx: tuple[int, int],
    *,
    flip_sites: tuple[int, ...] = (),
) -> None:
    """Render one tile's printed word bits at ``origin_yx`` of ``grid``."""
    positions = pilots.word_site_cells_yx(SPEC.family_seed)
    values = pilots.word_values(SPEC.seed, (counter,), SPEC.plane)[0].copy()
    for site in flip_sites:
        values[site] ^= 1
    grid[
        origin_yx[0] + positions[:, 0], origin_yx[1] + positions[:, 1]
    ] = values


def test_stage_a_hypotheses_declares_the_complete_slot_grid() -> None:
    # 200x200: 9 slots x (64x64 declared phases) x 4 orientations.
    assert stage_a_hypotheses((200, 200)) == 9 * 4096 * 4 == 147_456
    # 128x200: 6 slots per orientation (2x3 rot0/rot2, 3x2 rot1/rot3),
    # each declared at 64x64 phases: 4 x 6 x 4096.
    assert stage_a_hypotheses((128, 200)) == 6 * 4096 * 4 == 98_304
    # 70x70: one slot, 7x7 fitting phases, 4 orientations.
    assert stage_a_hypotheses((70, 70)) == 196
    # 64x64: one slot, one phase, 4 orientations.
    assert stage_a_hypotheses((64, 64)) == 4
    # No full slot fits: empty domain.
    assert stage_a_hypotheses((63, 200)) == 0


def test_multi_slot_sweep_decodes_away_from_a_masked_centre() -> None:
    rng = np.random.default_rng(20260731)
    bits = rng.integers(0, 2, (200, 200), dtype=np.uint8)
    # Real reference words for the 3x3 fully contained tile grid of an
    # origin-aligned 200-cell window on page 0.
    for tile_y in range(3):
        for tile_x in range(3):
            _paint_word(
                bits,
                SPEC.tile_counter(0, tile_y, tile_x),
                (64 * tile_y, 64 * tile_x),
            )
    mask = np.ones((200, 200), dtype=bool)
    mask[64:128, 64:128] = False    # the historically selected centre slot

    result = stage_a(bits, mask, SPEC, WINDOW_BUDGET)

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
        bits, SPEC.tile_counter(0, 0, 0), (0, 0),
        flip_sites=(3, 17, 42, 68, 91),
    )
    # Clean rot1 seed: paint into the rot1-oriented frame at slot (2, 2)
    # and rotate back (the two painted regions are disjoint).
    oriented = np.rot90(bits, 1).copy()
    _paint_word(oriented, SPEC.tile_counter(0, 5, 5), (128, 128))
    bits = np.ascontiguousarray(np.rot90(oriented, -1))
    mask = np.ones((200, 200), dtype=bool)

    result = stage_a(bits, mask, SPEC, WINDOW_BUDGET)

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


def test_word_budget_alpha_arithmetic_covers_the_widened_domain() -> None:
    probe = WordAttemptBudget(1, 1e-3, "test/probe")
    single = probe.single_word_probability
    sphere = sum(math.comb(100, i) for i in range(14))
    assert single == math.ldexp(float(sphere), 18 - 100)
    # The alpha = 1e-3 union-bound ceiling admits 581,074 hypotheses.
    ceiling = math.floor(1e-3 / single)
    assert ceiling == 581_074
    WordAttemptBudget(ceiling, 1e-3, "test/at-ceiling")
    with pytest.raises(ValueError, match="exceeds"):
        WordAttemptBudget(ceiling + 1, 1e-3, "test/over-ceiling")
    # One window fits comfortably; the three-row discovery envelope fits
    # tightly (7.6e-4 < 1e-3); a fourth 200-cell row would refuse.
    assert WordAttemptBudget(
        147_456, 1e-3, "test/window").random_union_bound < 1e-3
    three_rows = WordAttemptBudget(3 * 147_456, 1e-3, "test/three-rows")
    assert three_rows.max_hypotheses == 442_368
    assert three_rows.random_union_bound < 1e-3
    assert 4 * 147_456 * single > 1e-3


def test_domain_envelope_word_counts_cover_every_row() -> None:
    config = PlacementConfig()
    rows = tuple(
        (spec, tuple(range(spec.max_pages)))
        for spec in registered_format_rows()
    )
    envelope = PlacementDomainEnvelope.resolve(rows, config)
    assert envelope.word_hypotheses == 3 * 147_456 == 442_368
    for spec, pages in rows:
        # resolve() re-runs the coverage check and the WordAttemptBudget
        # construction-refusal; not raising is the assertion.
        _budgets, word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
            spec, pages, 0, config, domain_envelope=envelope)
        assert word.max_hypotheses == envelope.word_hypotheses
        assert word.random_union_bound < (
            PROVISIONAL_V1_PLACEMENT_POLICY.word_familywise_false_accept)


def test_staged_slot_stages_partition_the_sweep() -> None:
    """v0.26: centre + rest partition exactly the all-slot candidate set."""
    from holo.receive import words as words_module

    rng = np.random.default_rng(20260731)
    bits = rng.integers(0, 2, (200, 200), dtype=np.uint8)
    for tile_y in range(3):
        for tile_x in range(3):
            _paint_word(
                bits,
                SPEC.tile_counter(0, tile_y, tile_x),
                (64 * tile_y, 64 * tile_x),
            )
    mask = np.ones((200, 200), dtype=bool)
    everything = stage_a(bits, mask, SPEC, WINDOW_BUDGET, slots="all")
    centre = stage_a(bits, mask, SPEC, WINDOW_BUDGET, slots="centre")
    rest = stage_a(bits, mask, SPEC, WINDOW_BUDGET, slots="rest")
    assert centre.hypotheses == everything.hypotheses == 147_456
    assert centre.candidates, "centre stage must decode the interior slot"
    union = set(map(repr, centre.candidates)) | set(map(repr, rest.candidates))
    assert union == set(map(repr, everything.candidates))
    assert not (set(map(repr, centre.candidates))
                & set(map(repr, rest.candidates)))
    with pytest.raises(ValueError):
        stage_a(bits, mask, SPEC, WINDOW_BUDGET, slots="bogus")

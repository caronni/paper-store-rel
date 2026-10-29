"""The foreign-identity null: a sibling row's seed reads nothing.

Ported 2026-09-05 from the v1 receiver's null batteries — the
wrong-keystream rung of its payload nulls and the sibling-row rungs of
its placement null battery, all deleted with that tree at 284ae3e and
readable at its parent.  Under FORMAT-SPACE the
canonical format id IS the AES seed, so a sibling is one
`resolve_format_ref` call away: its keystream, its tile scramble and its
slot permutation all fork while the pilot lattice stays put.  True
evidence read against one must yield ZERO certificates and ZERO
placements, and the refusal has to be the decoder's own — a shape that
never reaches the LDPC or the BCH would pass this test for free, so both
halves count the searched domain and the decoder's own calls.
"""

from __future__ import annotations

import numpy as np
import pytest

from holo.receiver.format import tile_codec
from holo.receiver.format.identity import build_site_geometry, resolve_format_ref
from holo.receiver.plugins import cold, place, pose, tiles, words

TRUE_ROW = "c3-k-r0550@7x7"

#: (sibling ref, does it keep the true row's page geometry).  The TWIN
#: forks the printed pitch alone, so cells, tile counter and site lattice
#: all match and the seed is the only variable; the second forks the tile
#: matrix as well, which is the deleted battery's own construction.
SIBLING_ROWS = (("c2-k-r0550@7x7", True), ("c3-k-r0550@8x8", False))
SIBLING_REFS = tuple(ref for ref, _same in SIBLING_ROWS)

#: Cold correlation searches the whole page, so its rungs use the small
#: row test_h3_plugins_placement drives, and its own geometric twin.
TINY_ROW = "c3-k-r0550@2x2"
TINY_TWIN = "c2-k-r0550@2x2"

PIN_TILE = (3, 5)
NULL_TILES = ((3, 5), (1, 2), (0, 0))
USER_BITS_SEED = 11
HARD_LLR = 4.0

WORD_ORIGIN_YX = (128, 192)
WORD_SHAPE = (128, 128)

COLD_FRAGMENT_CELLS = 96
COLD_ORIGIN_YX = (18, 27)

# a null that reaches the audit has already passed the cold gate, which
# is the false accept these rungs exist to catch
NULL_REASONS = frozenset(
    {"winner_failed_heldout_gate", "rival_gap_failed",
     "insufficient_support"})


def _bundle(format_ref: str) -> tuple:
    row = resolve_format_ref(format_ref)
    return row, build_site_geometry(row)


@pytest.fixture(scope="module")
def true_bundle() -> tuple:
    return _bundle(TRUE_ROW)


@pytest.fixture(scope="module")
def sibling_bundle():
    built: dict[str, tuple] = {}

    def bundle(format_ref: str) -> tuple:
        if format_ref not in built:
            built[format_ref] = _bundle(format_ref)
        return built[format_ref]

    return bundle


def _user_bits(row) -> np.ndarray:
    rng = np.random.default_rng(USER_BITS_SEED)
    return rng.integers(0, 2, size=row.streams[0].user_bits, dtype=np.uint8)


def _true_cut(true_bundle: tuple, ty: int, tx: int) -> tiles.TileCut:
    row, geometry = true_bundle
    field = tiles.printed_cells_for(row, geometry, 0, ty, tx,
                                    _user_bits(row))
    return tiles.TileCut(
        capture_id="synthetic", level_index=0, page=0, ty=ty, tx=tx,
        values=((2.0 * field.astype(np.float32) - 1.0)
                * np.float32(HARD_LLR)).reshape(-1, 1),
        observed_flat=np.arange(tile_codec.N_CELLS, dtype=np.uint16))


def _count_tile_decodes(monkeypatch) -> list[int]:
    calls = [0]
    decode_tile = tile_codec.decode_tile

    def counting(*args, **kwargs):
        calls[0] += 1
        return decode_tile(*args, **kwargs)

    monkeypatch.setattr(tile_codec, "decode_tile", counting)
    return calls


@pytest.mark.parametrize("sibling_ref,same_geometry", SIBLING_ROWS)
def test_a_sibling_row_forks_the_seed_and_keeps_the_site_lattice(
        true_bundle, sibling_bundle, sibling_ref, same_geometry):
    true_row, true_geometry = true_bundle
    row, geometry = sibling_bundle(sibling_ref)
    assert row.seed != true_row.seed
    assert row.sites_seed == true_row.sites_seed
    assert np.array_equal(geometry.word_cells_yx,
                          true_geometry.word_cells_yx)
    assert np.array_equal(geometry.shorten_flat, true_geometry.shorten_flat)
    assert tiles.k_eff_bits(row) == tiles.k_eff_bits(true_row)
    assert (row.cells_yx == true_row.cells_yx) is same_geometry
    assert (row.tile_counter(0, *PIN_TILE)
            == true_row.tile_counter(0, *PIN_TILE)) is same_geometry


def test_a_true_tile_certifies_under_its_own_row(true_bundle, monkeypatch):
    row, geometry = true_bundle
    calls = _count_tile_decodes(monkeypatch)
    result = tiles.attempt_tile(row, geometry,
                                (_true_cut(true_bundle, *PIN_TILE),),
                                "main", tiles.STAGE_SCAN)
    assert result.fact.outcome == tiles.OUTCOME_CERTIFIED
    assert result.certificate is not None
    assert np.array_equal(result.certificate.user_bits, _user_bits(row))
    assert calls[0] == 1


@pytest.mark.parametrize("sibling_ref", SIBLING_REFS)
def test_true_tile_evidence_certifies_nothing_under_a_sibling_seed(
        true_bundle, sibling_bundle, sibling_ref, monkeypatch):
    row, geometry = sibling_bundle(sibling_ref)
    calls = _count_tile_decodes(monkeypatch)
    for ty, tx in NULL_TILES:
        result = tiles.attempt_tile(row, geometry,
                                    (_true_cut(true_bundle, ty, tx),),
                                    "main", tiles.STAGE_SCAN)
        assert result.certificate is None
        assert result.fact.outcome == tiles.OUTCOME_FAILED
        # the channel is perfect and every payload cell is informative:
        # the refusal is the decoder's, never the attempt floor's
        assert result.fact.n_informative == (
            tile_codec.N_CELLS - row.n_sites)
        assert result.fact.syndrome_ok is False
        assert result.fact.crc_ok is not True
        assert result.fact.n_iters > 0
    assert calls[0] == len(NULL_TILES)


def _word_fragment(row) -> np.ndarray:
    page = words.ReferenceField(row).page(0)
    oy, ox = WORD_ORIGIN_YX
    return page.values[oy:oy + WORD_SHAPE[0],
                       ox:ox + WORD_SHAPE[1]].copy()


def test_a_true_fragment_places_by_word_under_its_own_row(true_bundle):
    row, _geometry = true_bundle
    outcome = words.stage_a(_word_fragment(row),
                            np.ones(WORD_SHAPE, bool), row)
    assert outcome.reason == "candidates"
    assert outcome.hypotheses == words.stage_a_hypotheses(WORD_SHAPE)
    assert len(outcome.candidates) == 4
    assert {c.page_origin_yx for c in outcome.candidates} == {WORD_ORIGIN_YX}
    assert {c.errors for c in outcome.candidates} == {0}


@pytest.mark.parametrize("sibling_ref", SIBLING_REFS)
def test_a_true_fragment_finds_no_word_under_a_sibling_seed(
        true_bundle, sibling_bundle, sibling_ref):
    true_row, _geometry = true_bundle
    row, _sibling_geometry = sibling_bundle(sibling_ref)
    outcome = words.stage_a(_word_fragment(true_row),
                            np.ones(WORD_SHAPE, bool), row)
    assert outcome.candidates == ()
    assert outcome.reason == "no_word_candidate"
    # the domain the control searched, searched again: every window BCH
    # ran and matched nothing, rather than being refused before the search
    assert outcome.hypotheses == words.stage_a_hypotheses(WORD_SHAPE)


def _cold_outcome(field: words.ReferenceField, evidence: np.ndarray,
                  bits: np.ndarray) -> object:
    shape = (COLD_FRAGMENT_CELLS, COLD_FRAGMENT_CELLS)
    return cold.correlate_patch(
        evidence, bits, np.ones(shape, bool), field, (0,), 10 ** 9,
        place.E022_SUPPORT_FLOOR_SITES, pose.ScoreMemo(field),
        place.GATE_SEARCH_TRUE, place.GATE_VALIDATION_TRUE,
        place.GATE_RIVAL_DECOY, place.GATE_MINIMUM_GAP,
        place.NEIGHBOR_RADIUS_CELLS, allow_overhang=False)


@pytest.fixture(scope="module")
def cold_patch() -> tuple:
    field = words.ReferenceField(resolve_format_ref(TINY_ROW))
    oy, ox = COLD_ORIGIN_YX
    bits = field.page(0).values[
        oy:oy + COLD_FRAGMENT_CELLS, ox:ox + COLD_FRAGMENT_CELLS].copy()
    return field, bits, 1.0 - 2.0 * bits.astype(np.float32)


def test_a_true_patch_correlates_cold_under_its_own_row(cold_patch):
    field, bits, evidence = cold_patch
    outcome = _cold_outcome(field, evidence, bits)
    assert outcome.accepted is True
    assert outcome.reason == "accepted"
    assert outcome.best is not None
    assert (outcome.best.page, outcome.best.origin_yx,
            outcome.best.rot_k) == (0, COLD_ORIGIN_YX, 0)


def test_a_true_patch_refuses_cold_correlation_under_a_sibling_seed(
        cold_patch):
    field, bits, evidence = cold_patch
    twin = words.ReferenceField(resolve_format_ref(TINY_TWIN))
    outcome = _cold_outcome(twin, evidence, bits)
    assert outcome.accepted is False
    assert outcome.reason in NULL_REASONS
    # the twin keeps the page geometry, so the domain is the control's
    assert outcome.hypotheses == _cold_outcome(
        field, evidence, bits).hypotheses

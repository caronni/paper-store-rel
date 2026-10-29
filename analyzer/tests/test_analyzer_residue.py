"""analyzer.residue — coverage, bands, census, rank (PLAN §1.2, W1a)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from analyzer import inputs as inputs_module
from analyzer import residue
from analyzer.types import (BAND_DEAD, BAND_LIVE, BAND_MARGINAL,
                            BAND_UNCLASSIFIED)

from ._analyzer_fixtures import (FRAGMENT_TX, RESIDUE_WITHHELD,
                                 fossil_i_inputs, fragment_run, needs_sim,
                                 residue_census, residue_run)


# ------------------------------------------------------------- synthetic

def _fake_inputs(tiles_yx, certified):
    """The slice of RunInputs `column_bands` reads: tiles, streams, certs."""
    streams = tuple(SimpleNamespace(stream_id=name, plane=index)
                    for index, name in enumerate(("C", "M", "Y")))
    return SimpleNamespace(
        tiles_yx=tiles_yx,
        row=SimpleNamespace(streams=streams),
        certificates={key: object() for key in certified})


def test_band_classes_over_a_synthetic_certificate_map():
    tiles_y, tiles_x = 20, 5
    certified = set()
    for ty in range(tiles_y):
        certified.add((0, ty, 0, "C"))                    # column 0: 20/20
        if ty < 15:
            certified.add((0, ty, 1, "C"))                # column 1: 15/20
        if ty < 10:
            certified.add((0, ty, 2, "C"))                # column 2: 10/20
        if ty < 2:
            certified.add((0, ty, 3, "C"))                # column 3: 2/20
        # column 4: 0/20
    run = _fake_inputs((tiles_y, tiles_x), certified)
    covered = np.ones((tiles_y, tiles_x), bool)
    classes = residue.column_bands(run, 0, covered)["C"]
    # 2/20 is 10% but its exact upper bound (0.28) does not clear 0.25, so
    # it stays `marginal`: `dead` is the evidence-backed class.
    assert list(classes) == [BAND_LIVE, BAND_LIVE, BAND_MARGINAL,
                             BAND_MARGINAL, BAND_DEAD]
    assert residue._clopper_pearson_upper(2, 20, residue.BAND_ALPHA) > 0.25
    assert residue._clopper_pearson_upper(1, 20, residue.BAND_ALPHA) < 0.25


def test_a_thinly_covered_column_is_unclassified():
    tiles_y, tiles_x = 20, 2
    run = _fake_inputs((tiles_y, tiles_x), set())
    covered = np.zeros((tiles_y, tiles_x), bool)
    covered[:11, 0] = True                     # below MIN_COVERED_PER_COLUMN
    covered[:12, 1] = True                     # exactly at it
    classes = residue.column_bands(run, 0, covered)["C"]
    assert list(classes) == [BAND_UNCLASSIFIED, BAND_DEAD]


def test_a_low_fraction_column_without_evidence_is_marginal_not_live():
    """DESIGN §3's literal `else live` would call this column live."""
    tiles_y, tiles_x = 12, 1
    certified = {(0, 0, 0, "C")}               # 1 of 12 = 8%
    run = _fake_inputs((tiles_y, tiles_x), certified)
    covered = np.ones((tiles_y, tiles_x), bool)
    upper = residue._clopper_pearson_upper(1, 12, residue.BAND_ALPHA)
    assert upper > residue.BAND_DEAD_BOUND, "the exact bound does not close"
    assert list(residue.column_bands(run, 0, covered)["C"]) == [BAND_MARGINAL]


def test_band_any_is_the_cross_stream_union():
    tiles_y, tiles_x = 20, 2
    certified = {(0, ty, tx, s)
                 for ty in range(tiles_y) for tx in range(tiles_x)
                 for s in ("C", "M")}
    certified -= {(0, ty, 0, "C") for ty in range(tiles_y)}
    run = _fake_inputs((tiles_y, tiles_x), certified)
    covered = np.ones((tiles_y, tiles_x), bool)
    bands = residue.column_bands(run, 0, covered)
    assert bands["C"][0] == BAND_DEAD and bands["M"][0] == BAND_LIVE
    assert bands["any"][0] == BAND_DEAD
    assert bands["any"][1] == BAND_DEAD, "Y is dead in both columns"


def test_band_runs_are_maximal():
    classes = [BAND_LIVE, BAND_LIVE, BAND_DEAD, BAND_DEAD, BAND_DEAD,
               BAND_LIVE]
    assert residue.band_runs(classes) == (
        (BAND_LIVE, 0, 1), (BAND_DEAD, 2, 4), (BAND_LIVE, 5, 5))


def test_discriminating_mask_follows_the_corrected_label_arithmetic():
    """Word states 0 and 3 discriminate nothing; dust states do (DESIGN §1)."""
    from holo.receiver.format import tile_codec
    states = np.array([0, 3, 1, 2, 4, 5, 6, 7], np.uint8)
    bits = tile_codec.states_to_planes(states).reshape(1, -1, 3)
    known = np.ones_like(bits, bool)
    c_mask = residue.discriminating_mask(bits, known, "C")[0]
    m_mask = residue.discriminating_mask(bits, known, "M")[0]
    y_mask = residue.discriminating_mask(bits, known, "Y")[0]
    assert list(states[c_mask]) == [1, 2, 5, 6]
    assert list(states[m_mask]) == [1, 2, 5, 6]
    assert list(states[y_mask]) == [4, 5, 6, 7]
    # An unknown sibling removes a C/M label but not a Y one.
    known[0, 2, 1] = False
    assert not residue.discriminating_mask(bits, known, "C")[0, 2]
    assert residue.discriminating_mask(bits, known, "Y")[0, 4]


def test_target_specs_select_from_the_residue():
    from analyzer.types import LedgerRow

    def row(tx, stream, certified, band):
        return LedgerRow(
            page=0, ty=0, tx=tx, stream_id=stream, esi=0, covered=True,
            certified_by_production=certified, source=None, band=band,
            band_any=band, neighbours_certified=0, siblings_certified=(),
            known_cells_in_halo=0, n_discriminating_labels=0,
            production_attempts={}, metadata_known=True)

    rows = [row(0, "C", True, BAND_LIVE), row(1, "C", False, BAND_DEAD),
            row(2, "Y", False, BAND_MARGINAL)]
    rows.append(LedgerRow(
        page=0, ty=0, tx=3, stream_id="Y", esi=0, covered=False,
        certified_by_production=False, source=None, band=BAND_UNCLASSIFIED,
        band_any=BAND_UNCLASSIFIED, neighbours_certified=0,
        siblings_certified=(), known_cells_in_halo=0,
        n_discriminating_labels=0, production_attempts={},
        metadata_known=True))
    assert len(residue.residue_rows(rows)) == 2, "uncovered is never a target"
    assert [r.tx for r in residue.target_rows(rows, "band:dead")] == [1]
    assert [r.tx for r in residue.target_rows(rows, "stream:Y")] == [2]
    with pytest.raises(ValueError):
        residue.target_rows(rows, "nonsense")


def test_target_conjunction_grammar():
    """W8 B5: atoms joined by `+`, ANDed over the residue.

    The population every per-sibling-state mechanism needs — the open C
    rows of the dead band whose M and Y are both certified — had no
    grammar before this and had to be written out as a list file.
    """
    from analyzer.types import LedgerRow

    def row(tx, stream, band, siblings):
        return LedgerRow(
            page=0, ty=0, tx=tx, stream_id=stream, esi=0, covered=True,
            certified_by_production=False, source=None, band=band,
            band_any=band, neighbours_certified=0,
            siblings_certified=siblings, known_cells_in_halo=0,
            n_discriminating_labels=0, production_attempts={},
            metadata_known=True)

    rows = [row(0, "C", BAND_DEAD, ("M", "Y")),      # the C-dead-sibs row
            row(1, "C", BAND_DEAD, ("M",)),          # dead, Y still open
            row(2, "C", BAND_LIVE, ("M", "Y")),
            row(3, "Y", BAND_DEAD, ("C", "M"))]
    assert [r.tx for r in residue.target_rows(rows, "band:dead+stream:C")] \
        == [0, 1]
    assert [r.tx for r in residue.target_rows(rows, "stream:C+band:dead")] \
        == [0, 1], "order does not matter"
    assert [r.tx for r in
            residue.target_rows(rows, "stream:C+siblings:M,Y")] == [0, 2]
    assert [r.tx for r in
            residue.target_rows(rows, "stream:C+siblings:Y,M")] == [0, 2]
    assert [r.tx for r in
            residue.target_rows(rows,
                                "band:dead+stream:C+siblings:M,Y")] == [0]
    assert [r.tx for r in residue.target_rows(rows, "stream:C+siblings:M")] \
        == [1], "siblings is the SET, not a membership test"
    for bad in ("band:dead+nonsense", "nonsense+band:dead", "band", "+"):
        with pytest.raises(ValueError):
            residue.target_rows(rows, bad)


# ------------------------------------------- a withheld residue (TIER S)
# The receiver's colour sim decoded into a run dir, `RESIDUE_WITHHELD`'s
# certificates taken out of its snapshot (2026-10-09).  Sheet I's 22-key
# residue is a record (PAGE-FIELD-PLAN A1b).

@needs_sim
def test_the_census_finds_the_covered_residue_rows():
    run = residue_run()
    rows = residue_census()
    assert len(rows) == 10 * 10 * 3 == 300
    assert sum(row.covered for row in rows) == 300
    assert sum(row.certified_by_production for row in rows) == (
        300 - len(RESIDUE_WITHHELD))
    residue_rows = residue.residue_rows(rows)
    assert {row.key for row in residue_rows} == set(RESIDUE_WITHHELD)
    assert all(row.verdict == "open" for row in rows), "no unscoreable row"
    assert all(row.metadata_known for row in rows)
    keys = [(r.page, r.ty, r.tx, r.stream_id) for r in rows]
    assert keys == sorted(keys), "order is pinned (page, ty, tx, stream)"
    assert all(row.esi == run.esi(row.key) for row in rows)


@needs_sim
def test_the_census_columns_are_the_ones_design_section_3_names():
    run = residue_run()
    rows = {row.key: row for row in residue_census()}
    target = rows[(0, 2, 5, "Y")]
    # Ten covered tiles per column, under MIN_COVERED_PER_COLUMN: a
    # ten-tile page classifies no band (the band grammar is pinned on
    # hand-built rows above).
    assert residue.MIN_COVERED_PER_COLUMN > 10
    assert target.band == BAND_UNCLASSIFIED
    assert target.band_any == BAND_UNCLASSIFIED
    assert target.neighbours_certified == 8
    assert target.siblings_certified == ("C", "M")
    # Y halo is 32 cells; the target tile's payload is the one unknown
    # (the row's own count, which is sheet I's 3,976 too).
    n_payload = int(np.count_nonzero(residue.payload_cell_mask(run)))
    assert target.known_cells_in_halo == 128 * 128 - n_payload
    assert target.n_discriminating_labels > 40, "the §4.8 selection floor"
    corner = rows[(0, 0, 0, "C")]
    # A page corner has 3 neighbours; (0, 0, 1, C) is withheld too.
    assert corner.neighbours_certified == 2
    assert corner.known_cells_in_halo < target.known_cells_in_halo


def test_i_own_payload_never_labels_itself():
    """Sheet I's identity, every tile-stream certified (F3): (26, 18)'s
    whole Y halo is known, so the counts are the format's own."""
    run = fossil_i_inputs()
    known, disc = residue.halo_label_counts(run, 0, 26, 18, "Y")
    bits, mask = residue._projection_page(run, 0)
    own = residue._own_payload_counts(run, 0, 26, 18, "Y")
    assert own[0] == 3976, "the tile is certified, so its payload is known"
    assert known == 128 * 128 - 3976
    assert disc + own[1] == int(np.count_nonzero(
        residue.discriminating_mask(bits[26 * 64 - 32:27 * 64 + 32,
                                         18 * 64 - 32:19 * 64 + 32],
                                    mask[26 * 64 - 32:27 * 64 + 32,
                                         18 * 64 - 32:19 * 64 + 32], "Y")))


@needs_sim
def test_the_census_carries_the_report_rank_without_recomputing_it():
    """DESIGN §3: the row names both ranks; only the cross-check costs."""
    rows = residue_census()
    assert all(row.rank_report == 78 for row in rows[:10])
    assert all(row.rank_recomputed is None for row in rows[:10])


def test_i_rank_report_equals_the_recomputed_rank():
    check = residue.rank_check(fossil_i_inputs())
    assert check["rank_report"] == 5277
    assert check["rank_recomputed"] == 5277
    assert check["agree"] is True


# ----------------------------------------------- a fragment (TIER S)

@needs_sim
def test_the_census_excludes_uncovered_tiles_from_the_targets():
    """Sheet J's uncovered path on one page: the sim run with only the
    placements left of tile column `FRAGMENT_TX`, and only the
    certificates on the tiles they cover."""
    run = fragment_run()
    rows = residue.census(run)
    assert len(rows) == 10 * 10 * 3
    covered = [row for row in rows if row.covered]
    uncovered = [row for row in rows if not row.covered]
    assert covered and uncovered
    assert all(row.tx < FRAGMENT_TX for row in covered)
    assert all(row.verdict == "uncovered" for row in uncovered)
    assert all(row.known_cells_in_halo == 0 for row in uncovered)
    targets = residue.residue_rows(rows)
    assert all(row.covered for row in targets)
    per_page = {
        page: int((inputs_module.page_tile_coverage(run, page) > 0).sum())
        for page in run.live_pages}
    assert sum(per_page.values()) * 3 == len(covered)

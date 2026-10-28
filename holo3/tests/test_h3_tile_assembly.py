from __future__ import annotations

import numpy as np
import pytest

from holo3.lib.geometry import TILE_CELLS
from holo3.plugins import tiles
from holo3.tests import _h3_facts, _h3_support

CAPTURE_ID = _h3_facts.CAPTURE_ID
WID_A = (CAPTURE_ID, 0, 0, (0, 0, TILE_CELLS, TILE_CELLS))
WID_B = (CAPTURE_ID, 0, 0, (0, TILE_CELLS, TILE_CELLS, 2 * TILE_CELLS))
ADDRESS = (0, 0, 0)
LEVEL = 0

LLR_A = 3.0
LLR_B = -3.0
PAYLOAD_CELLS = 3996
HALF = TILE_CELLS // 2


def _cells(y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
    grid = np.stack(np.meshgrid(np.arange(y0, y1), np.arange(x0, x1),
                                indexing="ij"), axis=-1)
    return grid.reshape(-1, 2).astype(np.int64)


def _full() -> np.ndarray:
    return _cells(0, TILE_CELLS, 0, TILE_CELLS)


def _store(*rows: tuple) -> object:
    engine = _h3_facts.new_engine()
    engine._fold(_h3_facts.capture())
    for wid, loss, printed, cells in rows:
        engine._fold(_h3_facts.evidence(wid=wid, loss=loss, printed=printed,
                                        cells=cells))
    return engine


def _assemble(engine: object) -> tiles.TileCut:
    page, ty, tx = ADDRESS
    cut = tiles.assemble_tile(engine, page, ty, tx, CAPTURE_ID, LEVEL)
    assert cut is not None
    return cut


def _owned_columns(cut: tiles.TileCut) -> tuple[np.ndarray, np.ndarray]:
    flat = np.asarray(cut.observed_flat, np.int64)
    return flat // TILE_CELLS, flat % TILE_CELLS


def test_a_single_covering_window_owns_every_payload_cell_of_the_tile():
    cut = _assemble(_store((WID_A, 0.10, LLR_A, _full())))
    _h3_support.assert_golden("payload cells cut from one window",
                              int(cut.values.shape[0]), PAYLOAD_CELLS)
    assert np.array_equal(np.unique(cut.values), np.array([LLR_A],
                                                          np.float32))
    assert (cut.capture_id, cut.level_index) == (CAPTURE_ID, LEVEL)


def test_the_better_heldout_loss_wins_the_contested_cell():
    cut = _assemble(_store((WID_A, 0.10, LLR_A, _full()),
                           (WID_B, 0.20, LLR_B, _full())))
    assert np.array_equal(np.unique(cut.values), np.array([LLR_A],
                                                          np.float32))
    assert int(cut.values.shape[0]) == PAYLOAD_CELLS, (
        "the union of the two windows is one cut, not two: every cell is "
        "owned exactly once")


def test_the_loser_of_the_contest_still_owns_the_cells_nobody_contests():
    cut = _assemble(_store((WID_A, 0.10, LLR_A, _cells(0, TILE_CELLS, 0,
                                                       HALF)),
                           (WID_B, 0.20, LLR_B, _full())))
    _rows, columns = _owned_columns(cut)
    values = np.asarray(cut.values, np.float32).reshape(-1)
    left = columns < HALF
    assert np.all(values[left] == np.float32(LLR_A))
    assert np.all(values[~left] == np.float32(LLR_B))
    assert int(cut.values.shape[0]) == PAYLOAD_CELLS


def test_a_later_better_window_revises_ownership_before_certification():
    engine = _store((WID_A, 0.10, LLR_A, _full()),
                    (WID_B, 0.20, LLR_B, _full()))
    before = _assemble(engine)
    assert np.array_equal(np.unique(before.values),
                          np.array([LLR_A], np.float32))
    engine._fold(_h3_facts.evidence(wid=WID_B, loss=0.05, printed=LLR_B,
                                    cells=_full()))
    after = _assemble(engine)
    assert np.array_equal(np.unique(after.values),
                          np.array([LLR_B], np.float32)), (
        "ownership is revisable until certification: assembly happens at "
        "fire time over the standing evidence, never frozen (item 12)")
    assert after.observed_flat.tobytes() == before.observed_flat.tobytes()


def test_a_window_that_gets_worse_hands_its_cells_back():
    engine = _store((WID_A, 0.10, LLR_A, _full()),
                    (WID_B, 0.20, LLR_B, _full()))
    engine._fold(_h3_facts.evidence(wid=WID_A, loss=0.90, printed=LLR_A,
                                    cells=_full()))
    cut = _assemble(engine)
    assert np.array_equal(np.unique(cut.values),
                          np.array([LLR_B], np.float32))


def test_an_equal_loss_contest_is_broken_by_the_window_extent_not_by_luck():
    first = _assemble(_store((WID_A, 0.10, LLR_A, _full()),
                             (WID_B, 0.10, LLR_B, _full())))
    second = _assemble(_store((WID_B, 0.10, LLR_B, _full()),
                              (WID_A, 0.10, LLR_A, _full())))
    assert np.array_equal(np.unique(first.values),
                          np.array([LLR_A], np.float32))
    assert first.values.tobytes() == second.values.tobytes(), (
        "the tie-break is the window extent, so the fold order of the two "
        "evidence rows cannot change the cut")


def test_a_refused_window_covers_nothing_and_never_owns_a_cell():
    engine = _h3_facts.new_engine()
    engine._fold(_h3_facts.capture())
    engine._fold(_h3_facts.evidence(wid=WID_A, loss=0.01, printed=LLR_A,
                                    cells=_full(), accepted=False))
    engine._fold(_h3_facts.evidence(wid=WID_B, loss=0.50, printed=LLR_B,
                                    cells=_full()))
    cut = _assemble(engine)
    assert np.array_equal(np.unique(cut.values),
                          np.array([LLR_B], np.float32))


def test_a_tile_no_window_covers_assembles_to_nothing():
    engine = _store((WID_A, 0.10, LLR_A, _full()))
    assert tiles.assemble_tile(engine, 0, 6, 6, CAPTURE_ID, LEVEL) is None


def test_the_cut_carries_flat_in_tile_indices_and_no_duplicate_cell():
    cut = _assemble(_store((WID_A, 0.10, LLR_A, _full()),
                           (WID_B, 0.20, LLR_B, _full())))
    flat = np.asarray(cut.observed_flat, np.int64)
    assert flat.dtype == np.int64 and cut.observed_flat.dtype == np.uint16
    assert len(set(flat.tolist())) == flat.size
    assert int(flat.min()) >= 0
    assert int(flat.max()) < TILE_CELLS * TILE_CELLS
    assert np.array_equal(flat, np.sort(flat))


def test_assembly_reads_the_store_and_writes_nothing_back_to_it():
    engine = _store((WID_A, 0.10, LLR_A, _full()),
                    (WID_B, 0.20, LLR_B, _full()))
    before, _hold_before = _h3_facts.store_snapshot(engine)
    _assemble(engine)
    _assemble(engine)
    after, _hold_after = _h3_facts.store_snapshot(engine)
    _h3_support.assert_golden("store cells assembly wrote",
                              _h3_facts.cells_written(before, after), ())


def test_two_assemblies_of_one_unchanged_store_are_byte_identical():
    engine = _store((WID_A, 0.10, LLR_A, _full()),
                    (WID_B, 0.20, LLR_B, _full()))
    first = _assemble(engine)
    second = _assemble(engine)
    assert first.values.tobytes() == second.values.tobytes()
    assert first.observed_flat.tobytes() == second.observed_flat.tobytes()


@pytest.mark.parametrize("symbol", ("assemble_tile", "assemble_union"))
def test_assembly_is_a_free_function_of_the_store_not_a_stored_stage(symbol):
    assert callable(getattr(tiles, symbol))
    assert not hasattr(tiles, "FREEZE_DESCRIPTOR")

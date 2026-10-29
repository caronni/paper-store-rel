from __future__ import annotations

import numpy as np
import pytest

from holo.receiver.lib.owners import freeze_page_owners

PAGE_SHAPE_YX = (16, 20)

# the shape calibrate.freeze_owners and tiles.assemble_tile build:
# (heldout_logloss, window-extent tuple, region_index, plane)
BASE_KEY = (0.5, (1, 2), 3, "K")
KEY_LADDER = (
    ("heldout_logloss", (0.4, (1, 2), 3, "K")),
    ("window_extent", (0.5, (0, 2), 3, "K")),
    ("region_index", (0.5, (1, 2), 2, "K")),
    ("plane", (0.5, (1, 2), 3, "C")),
)


def _candidate(window_index: int, page: int, cells: object,
               values: object) -> tuple:
    cells_yx = np.asarray(cells, np.int64).reshape(-1, 2)
    return (window_index, page, cells_yx,
            np.arange(cells_yx.shape[0], dtype=np.int32),
            np.asarray(values, np.float32).reshape(cells_yx.shape[0], 1)
            if cells_yx.shape[0] else np.zeros((0, 1), np.float32))


def _overlapping_candidates() -> list[tuple]:
    return [
        _candidate(0, 0, [[1, 1], [2, 2]], [10.0, 20.0]),
        _candidate(1, 0, [[2, 2], [3, 3]], [21.0, 30.0]),
        _candidate(2, 1, [[0, 0]], [40.0]),
        _candidate(3, 0, [], []),
    ]


def _as_rows(frozen: tuple) -> list[tuple]:
    return [(page, cells.tolist(), values.ravel().tolist(),
             windows.tolist(), rows.tolist())
            for page, cells, values, windows, rows in frozen]


def test_one_owner_per_page_cell_with_the_page_axis_sorted():
    frozen = freeze_page_owners(_overlapping_candidates(), PAGE_SHAPE_YX)
    assert [row[0] for row in frozen] == [0, 1]
    for page, cells, values, windows, rows in frozen:
        assert cells.dtype == np.int32
        assert values.dtype == np.float32
        assert windows.dtype == np.int32 and rows.dtype == np.int32
        assert cells.shape[0] == values.shape[0] == windows.size == rows.size
        keys = cells[:, 0].astype(np.int64) * PAGE_SHAPE_YX[1] + cells[:, 1]
        assert np.array_equal(keys, np.unique(keys))


def test_without_a_declared_order_the_first_writer_in_arrival_order_wins():
    rows = _overlapping_candidates()
    arrival = _as_rows(freeze_page_owners(rows, PAGE_SHAPE_YX))
    permuted = _as_rows(freeze_page_owners(
        [rows[index] for index in (3, 1, 0, 2)], PAGE_SHAPE_YX))
    assert arrival[0][2] == [10.0, 20.0, 30.0]
    assert arrival[0][3] == [0, 0, 1]
    assert permuted[0][2] == [10.0, 21.0, 30.0]
    assert permuted[0][3] == [0, 1, 1]
    assert arrival != permuted


def test_the_declared_total_order_makes_ownership_permutation_invariant():
    rows = _overlapping_candidates()
    keys = [(1.0,), (0.5,), (0.0,), (2.0,)]
    reference = _as_rows(freeze_page_owners(rows, PAGE_SHAPE_YX, keys))
    assert reference[0][2] == [10.0, 21.0, 30.0]
    assert reference[0][3] == [0, 1, 1]
    for permutation in ((3, 1, 0, 2), (2, 3, 1, 0), (1, 0, 3, 2),
                        (3, 2, 1, 0)):
        shuffled = _as_rows(freeze_page_owners(
            [rows[index] for index in permutation], PAGE_SHAPE_YX,
            [keys[index] for index in permutation]))
        assert shuffled == reference, permutation


@pytest.mark.parametrize("component, rival_key", KEY_LADDER)
def test_every_component_of_the_freeze_key_is_separately_load_bearing(
        component, rival_key):
    pair = [_candidate(7, 0, [[5, 5]], [70.0]),
            _candidate(9, 0, [[5, 5]], [90.0])]
    forward = freeze_page_owners(pair, PAGE_SHAPE_YX, [BASE_KEY, rival_key])
    assert int(forward[0][3][0]) == 9, component
    assert float(forward[0][2][0][0]) == 90.0
    reversed_rows = freeze_page_owners(pair[::-1], PAGE_SHAPE_YX,
                                       [rival_key, BASE_KEY])
    assert int(reversed_rows[0][3][0]) == 9, component
    assert float(reversed_rows[0][2][0][0]) == 90.0


def test_an_exact_key_tie_falls_back_to_arrival_order():
    pair = [_candidate(7, 0, [[5, 5]], [70.0]),
            _candidate(9, 0, [[5, 5]], [90.0])]
    assert int(freeze_page_owners(
        pair, PAGE_SHAPE_YX, [BASE_KEY, BASE_KEY])[0][3][0]) == 7
    assert int(freeze_page_owners(
        pair[::-1], PAGE_SHAPE_YX, [BASE_KEY, BASE_KEY])[0][3][0]) == 9


def test_freezing_an_already_frozen_page_is_a_fixed_point():
    candidates = [_candidate(0, 0, [[1, 1], [2, 2], [7, 3]],
                             [10.0, 20.0, 70.0])]
    first = freeze_page_owners(candidates, PAGE_SHAPE_YX)
    page, cells, values, windows, rows = first[0]
    again = freeze_page_owners(
        [(int(windows[0]), page, cells.astype(np.int64), rows, values)],
        PAGE_SHAPE_YX)
    assert np.array_equal(again[0][1], cells)
    assert np.array_equal(again[0][2], values)
    assert np.array_equal(again[0][3], windows)
    assert np.array_equal(again[0][4], rows)


def test_candidates_with_no_cells_contribute_no_page():
    assert freeze_page_owners([], PAGE_SHAPE_YX) == ()
    assert freeze_page_owners([_candidate(0, 0, [], [])],
                              PAGE_SHAPE_YX) == ()


def test_the_page_key_uses_the_declared_page_width():
    wide = [_candidate(0, 0, [[0, 19]], [1.0]),
            _candidate(1, 0, [[1, 0]], [2.0])]
    frozen = freeze_page_owners(wide, PAGE_SHAPE_YX)
    assert frozen[0][1].tolist() == [[0, 19], [1, 0]]
    assert frozen[0][2].ravel().tolist() == [1.0, 2.0]
    narrow = freeze_page_owners(wide, (16, 5))
    assert narrow[0][1].tolist() != [[0, 19], [1, 0]]


def test_per_cell_value_rows_survive_the_ownership_selection():
    values = np.arange(6, dtype=np.float32).reshape(3, 2)
    candidates = [(0, 0, np.array([[1, 1], [2, 2], [3, 3]], np.int64),
                   np.arange(3, dtype=np.int32), values)]
    frozen = freeze_page_owners(candidates, PAGE_SHAPE_YX)
    assert frozen[0][2].shape == (3, 2)
    assert np.array_equal(frozen[0][2], values)


def test_a_repeated_cell_inside_one_candidate_keeps_its_first_row():
    candidates = [_candidate(0, 0, [[4, 4], [4, 4], [5, 5]],
                             [1.0, 2.0, 3.0])]
    frozen = freeze_page_owners(candidates, PAGE_SHAPE_YX)
    assert frozen[0][1].tolist() == [[4, 4], [5, 5]]
    assert frozen[0][2].ravel().tolist() == [1.0, 3.0]
    assert frozen[0][4].tolist() == [0, 2]


def test_pages_come_back_in_ascending_page_order_whatever_the_input_order():
    candidates = [_candidate(0, 5, [[1, 1]], [1.0]),
                  _candidate(1, 2, [[1, 1]], [2.0]),
                  _candidate(2, 9, [[1, 1]], [3.0]),
                  _candidate(3, 0, [[1, 1]], [4.0])]
    assert [row[0] for row in
            freeze_page_owners(candidates, PAGE_SHAPE_YX)] == [0, 2, 5, 9]
    assert [row[0] for row in freeze_page_owners(
        candidates[::-1], PAGE_SHAPE_YX)] == [0, 2, 5, 9]

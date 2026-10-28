from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np


def freeze_page_owners(
    candidates: Iterable[
        tuple[int, int, np.ndarray, np.ndarray, np.ndarray]],
    page_shape_yx: tuple[int, int],
    order_keys: Sequence[tuple[object, ...]] | None = None,
) -> tuple[tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray], ...]:
    rows = list(candidates)
    if order_keys is not None:
        rows = [rows[index] for index in
                sorted(range(len(rows)), key=order_keys.__getitem__)]
    width = int(page_shape_yx[1])
    grouped: dict[
        int, list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
    ] = {}
    for window_index, page, cells_yx, row_indices, values in rows:
        cells = np.asarray(cells_yx, np.int64)
        if not cells.shape[0]:
            continue
        keys = cells[:, 0] * np.int64(width) + cells[:, 1]
        grouped.setdefault(int(page), []).append((
            keys,
            np.full(keys.size, int(window_index), np.int32),
            np.asarray(row_indices, np.int32),
            np.asarray(values),
        ))
    output: list[
        tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    for page in sorted(grouped):
        parts = grouped[page]
        keys = np.concatenate([part[0] for part in parts])
        unique_keys, owner_rows = np.unique(keys, return_index=True)
        window_indices = np.concatenate(
            [part[1] for part in parts])[owner_rows]
        row_indices = np.concatenate(
            [part[2] for part in parts])[owner_rows]
        values = np.concatenate(
            [part[3] for part in parts], axis=0)[owner_rows]
        cells = np.column_stack((
            unique_keys // np.int64(width),
            unique_keys % np.int64(width),
        )).astype(np.int32, copy=False)
        output.append((page, cells, values, window_indices, row_indices))
    return tuple(output)

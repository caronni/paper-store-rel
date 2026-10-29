"""The Xerox DocuColor-class reading (EFF, 2005) and its parity search.

The EFF's DocuColor decoding guide reads a 15-column x 8-row dot block,
repeated over the page: row 1 and column 1 are parity, rows 2–8 carry a
7-bit value per column (row 2 the most significant bit), and every data
column and data row has ODD parity (the corner belongs to neither — all
fifteen columns and all eight rows odd is impossible, the parities would
disagree).  Column meanings as implemented here, after that guide:
2 minute, 5 hour, 6 day, 7 month, 8 year (two digits), 11–14 the serial
number, two decimal digits per column (a value 0–99 in binary — two BCD
nibbles would not fit seven bits), read 14 13 12 11; 3, 4, 9, 15 unused,
10 a separator.  This module never saw a DocuColor print: the
mapping is the guide's as recalled, the parity test is what decides.

The search reads every placement of the block on a site matrix — every
origin, the eight orientations of the square's symmetry group, site
strides 1 and 2 — and keeps the blocks whose 21 parity constraints all
hold.  A random block passes with probability 2**-21 per parity sense,
so the expected number of chance hits is reported beside the hits.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

COLUMNS: int = 15
ROWS: int = 8
PARITY_CONSTRAINTS: int = (COLUMNS - 1) + (ROWS - 1)

#: A block with fewer dots than this in its data area (rows and columns
#: 2 on) is not a trial: an empty data area passes even parity
#: trivially (measured: the M281's sparse sites, 2026-10-09), and a
#: real block carries a separator column and five date fields.
MIN_DATA_DOTS: int = 10

#: The eight orientations: (col, row) -> (di, dj) as integer matrices.
ORIENTATIONS: tuple[tuple[tuple[int, int], tuple[int, int]], ...] = (
    ((1, 0), (0, 1)), ((-1, 0), (0, 1)), ((1, 0), (0, -1)), ((-1, 0), (0, -1)),
    ((0, 1), (1, 0)), ((0, -1), (1, 0)), ((0, 1), (-1, 0)), ((0, -1), (-1, 0)),
)


def encode(minute: int, hour: int, day: int, month: int, year2: int, serial8: str,
           *, separator: int = 0x7F) -> np.ndarray:
    """A DocuColor block (8 rows x 15 columns, 0/1) under this module's
    reading — the synthetic-test fixture and the decoder's inverse."""
    if len(serial8) != 8 or not serial8.isdigit():
        raise ValueError("serial8 must be eight decimal digits")
    values = [0] * (COLUMNS + 1)
    values[2], values[5], values[6], values[7], values[8] = minute, hour, day, month, year2
    values[10] = separator
    pairs = [serial8[k:k + 2] for k in range(0, 8, 2)]
    for col, pair in zip((14, 13, 12, 11), pairs):
        values[col] = int(pair)
    block = np.zeros((ROWS, COLUMNS), np.int8)
    for col in range(2, COLUMNS + 1):
        v = values[col]
        if not 0 <= v < 128:
            raise ValueError(f"column {col} value {v} does not fit 7 bits")
        for row in range(2, ROWS + 1):
            block[row - 1, col - 1] = (v >> (ROWS - row)) & 1
    for row in range(2, ROWS + 1):
        block[row - 1, 0] = 1 - (int(block[row - 1, 1:].sum()) & 1)
    for col in range(2, COLUMNS + 1):
        block[0, col - 1] = 1 - (int(block[1:, col - 1].sum()) & 1)
    return block


def parity_sense(block: np.ndarray) -> str | None:
    """'odd' or 'even' when every data row and column agrees, else None."""
    cols = block[:, 1:].sum(axis=0) & 1
    rows = block[1:, :].sum(axis=1) & 1
    if np.all(cols == 1) and np.all(rows == 1):
        return "odd"
    if np.all(cols == 0) and np.all(rows == 0):
        return "even"
    return None


def _two_digits(v: int) -> str | None:
    return f"{v:02d}" if v < 100 else None


def decode(block: np.ndarray) -> dict[str, object]:
    """Column values and this module's DocuColor reading of one block."""
    weights = 1 << np.arange(ROWS - 2, -1, -1)
    values = {col + 1: int(block[1:, col] @ weights) for col in range(1, COLUMNS)}
    digits = [_two_digits(values[c]) for c in (14, 13, 12, 11)]
    serial = None if any(d is None for d in digits) else "".join(digits)  # type: ignore[arg-type]
    minute, hour, day, month, year = values[2], values[5], values[6], values[7], values[8]
    plausible = (minute < 60 and hour < 24 and 1 <= day <= 31 and 1 <= month <= 12
                 and year < 100 and serial is not None)
    return {
        "column_values": {str(k): v for k, v in values.items()},
        "minute": minute, "hour": hour, "day": day, "month": month, "year_two_digit": year,
        "serial": serial,
        "fields_plausible": bool(plausible),
    }


@dataclass(frozen=True)
class Hit:
    origin_ij: tuple[int, int]
    orientation: int
    stride: int
    parity: str
    block: np.ndarray


def search(value_at: Callable[[np.ndarray, np.ndarray], np.ndarray],
           origins_ij: np.ndarray, *, strides: tuple[int, ...] = (1, 2),
           site_key: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None,
           ) -> tuple[list[Hit], int]:
    """Every parity-consistent block over ``origins_ij`` (n, 2).

    ``value_at(i, j)`` returns 1/0/-1 (unknown) per site; a placement
    touching an unknown site is not a trial.  On a folded (toroidal)
    cell ``site_key(i, j)`` names the cell site each position lands on,
    and a placement that visits one cell site twice is not a trial
    either — a block wrapped onto itself reads its own bits twice and
    passes parity by symmetry, not by chance (measured: 18 such
    "hits" on the VersaLink's 16 x 16 cell before this rule).  Returns
    the hits and the number of trials made."""
    cc, rr = np.meshgrid(np.arange(COLUMNS), np.arange(ROWS))
    hits: list[Hit] = []
    trials = 0
    for o, ((ci, cj), (ri, rj)) in enumerate(ORIENTATIONS):
        for stride in strides:
            di = stride * (cc * ci + rr * ri)
            dj = stride * (cc * cj + rr * rj)
            i = origins_ij[:, 0, None, None] + di[None]
            j = origins_ij[:, 1, None, None] + dj[None]
            blocks = value_at(i, j)
            full = np.all(blocks >= 0, axis=(1, 2))
            full &= (blocks[:, 1:, 1:] == 1).sum(axis=(1, 2)) >= MIN_DATA_DOTS
            if site_key is not None:
                keys = np.sort(site_key(i, j).reshape(len(i), -1), axis=1)
                full &= np.all(np.diff(keys, axis=1) != 0, axis=1)
            trials += int(full.sum())
            for n in np.flatnonzero(full):
                sense = parity_sense(blocks[n])
                if sense is not None:
                    hits.append(Hit(origin_ij=(int(origins_ij[n, 0]), int(origins_ij[n, 1])),
                                    orientation=o, stride=stride, parity=sense,
                                    block=blocks[n].astype(np.int8)))
    return hits, trials


def expected_chance_hits(trials: int) -> float:
    """Two parity senses, each 2**-21 per random trial."""
    return 2.0 * trials * 2.0 ** -PARITY_CONSTRAINTS

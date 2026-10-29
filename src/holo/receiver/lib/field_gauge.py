"""The page field's gauge, derived from the ink the pose is fit from.

The field is each plane's displacement relative to the frame the sampler
already uses, the pose, so what "zero" means is the POSE's ink
(docs/PAGE-FIELD-DESIGN.md §2.3, amended 2026-10-12; docs/CMY-DESIGN.md
R7).  The row's word '1' (`row.word_states[1]`) is its proxy, because
every colour row fits its pose on the word sites in a channel where that
word is the dark ink: cmy8's and cmy7's word is C and M overprinted,
read on luma, so the pose sits between them by construction and
`F_C + F_M = 0`, Y free; cmy's word is C alone, read on R
(`plugins/words.ADDRESSING_ON_R`), so the pose IS C's, `F_C = 0` by name
and M and Y are free, each relative to C (CMY-DESIGN §7 (f)).  No
weights: a pose on one ink needs none, and a two-ink word's pose is
between its planes by construction.

The derivation is a table per plane — which of the solve's two free
fields the plane reads, and at what sign — and every per-plane quantity
the solve publishes reads it: the fields, their uncertainty, and which
planes the page knows.  Pure, numpy only, no clock and no raster.
"""

from __future__ import annotations

import numpy as np

#: The three colour planes, in the order the format names them.
N_PLANES: int = 3

Gauge = tuple[np.ndarray, np.ndarray]


def word_planes(word_state: int) -> tuple[int, ...]:
    """The planes a colour row's word '1' prints, from its presence id
    (`row.word_states[1]`): cmy8's and cmy7's CM gives (0, 1), cmy's C
    gives (0,)."""
    return tuple(plane for plane in range(N_PLANES)
                 if int(word_state) >> plane & 1)


#: The v1 colour word, C and M overprinted: the gauge the solve takes
#: when its caller names none — every cmy8 and cmy7 row, and the
#: behaviour suite that states the solve's arithmetic.
CM_WORD_PLANES: tuple[int, ...] = word_planes(3)


def gauge_table(word: tuple[int, ...]) -> Gauge:
    """Per plane, the free field it reads and its coefficient there.

    Two word planes cancel: the first reads field 0 at +1, the second at
    -1, the third plane is field 1 at +1 — cmy8's C +1 and M -1 on 0, Y
    +1 on 1.  One word plane IS the pose: its coefficient is 0, so its
    rows inform only the window nuisances, and the other two are the two
    fields in plane order at +1 each — cmy's M on 0 and Y on 1.
    """
    word = tuple(int(plane) for plane in word)
    free = [plane for plane in range(N_PLANES) if plane not in word]
    column = np.zeros(N_PLANES, np.int64)
    coefficient = np.zeros(N_PLANES, np.float64)
    if len(word) == 2:
        coefficient[list(word)] = (1.0, -1.0)
        column[free] = 1
        coefficient[free] = 1.0
    elif len(word) == 1:
        column[free] = (0, 1)
        coefficient[free] = 1.0
    else:
        raise ValueError(
            f"page field: no gauge for a word printed in planes {word}")
    return column, coefficient


def held_planes(word: tuple[int, ...]) -> tuple[bool, ...]:
    """Per plane, whether the gauge holds it at the pose (coefficient
    0): cmy's C, none of cmy8's."""
    _column, coefficient = gauge_table(word)
    return tuple(bool(value == 0.0) for value in coefficient)


def plane_fields(free: np.ndarray, gauge: Gauge) -> list[np.ndarray]:
    """The three planes' fields from the two free ones: the field a plane
    reads, negated where its coefficient is, and the ZERO field for a
    plane the gauge holds at the pose."""
    column, coefficient = gauge
    return [free[column[plane]] if coefficient[plane] > 0.0
            else -free[column[plane]] if coefficient[plane] < 0.0
            else np.zeros_like(free[0]) for plane in range(N_PLANES)]


def plane_variances(variance: np.ndarray, gauge: Gauge) -> list[np.ndarray]:
    """The three planes' posterior variances from the two free fields':
    planes reading one field share its variance, and a plane the gauge
    holds at the pose has none."""
    column, coefficient = gauge
    return [variance[column[plane]] if coefficient[plane] != 0.0
            else np.zeros_like(variance[0]) for plane in range(N_PLANES)]


def known_planes(seen: np.ndarray, gauge: Gauge) -> np.ndarray:
    """Which planes a page with measurements of the planes `seen` knows.

    Planes reading one field stand together — under cmy8's gauge a
    measurement of C or of M is a measurement of both — and a plane the
    gauge holds at the pose is known BY NAME, measured or not: cmy's C
    field is zero by definition, a statement and not the absence of one.
    """
    column, coefficient = gauge
    read = {int(column[plane]) for plane in np.asarray(seen, np.int64)
            if coefficient[plane] != 0.0}
    return np.array([bool(coefficient[plane] == 0.0
                          or int(column[plane]) in read)
                     for plane in range(N_PLANES)])

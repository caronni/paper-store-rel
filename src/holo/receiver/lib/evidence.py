"""The page field's evidence table: one row per measurement, raw.

A row is ONE measurement of ONE plane on ONE tile from ONE capture: the
displacement of that plane's ink against the pose the measurement was
taken through, a flag per axis saying whether that axis was measured at
all, a weight, and where it came from.  Nothing is ever subtracted from
a row (`docs/PAGE-FIELD-DESIGN.md` §2.5, W8 R-C): the gauge that decides
what "zero" means and the nuisance that absorbs a window's own pose
error are the SOLVE's, because both are statements about a page and a
row is a statement about one window's photons.

The two masks are what keeps "unknown" apart from "zero".  A tier that
swept only x writes `measured_xy = (True, False)` and the solve reads
nothing from its y column; the alternative — a zero in the y column with
a positive weight — is a measurement of no displacement, which no tier
made (the review's F8).

Immutable and concatenable, and that is the whole surface: the table
carries no policy.  Immutable means the ARRAYS too, not just the
attribute names: a table is passed to the solve and to whatever
diagnostic wants to count it, and a column edited in place under one of
them would change the evidence of a page that had already been solved.
The columns are read-only VIEWS, so nothing can write THROUGH the table;
a builder that keeps its own reference to an array it passed in can still
write through that, so builders hand their columns over and forget them.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

import numpy as np

#: the columns, in the order `concat` and the constructor take them
COLUMNS = ("capture", "page", "tile_code", "plane", "delta_dots_xy",
           "measured_xy", "weight", "source", "window", "pose_generation")


@dataclass(frozen=True)
class Rows:
    """One page's measurements, as parallel arrays.

    `capture` and `window` are INDICES into the tables the caller holds
    (the capture ids in sorted order; the window ids of the collection
    that made the row), never the ids themselves: the field is not keyed
    by either, and an id that travelled into the estimator would be an
    invitation to key by it.  `delta_dots_xy` is in printed dots along
    the PAGE axes, `tile_code` is `ty * tiles_x + tx`.
    """

    capture: np.ndarray
    page: np.ndarray
    tile_code: np.ndarray
    plane: np.ndarray
    delta_dots_xy: np.ndarray
    measured_xy: np.ndarray
    weight: np.ndarray
    source: np.ndarray
    window: np.ndarray
    pose_generation: np.ndarray

    def __post_init__(self) -> None:
        n = np.asarray(self.capture).shape[0]
        for column in fields(self):
            value = np.asarray(getattr(self, column.name))
            if value.shape[0] != n:
                raise ValueError(
                    f"evidence column {column.name} has {value.shape[0]} "
                    f"rows against {n}")
        for column in ("delta_dots_xy", "measured_xy"):
            value = np.asarray(getattr(self, column))
            if value.ndim != 2 or value.shape[1] != 2:
                raise ValueError(
                    f"evidence column {column} is (n, 2) — x then y — "
                    f"not {value.shape}")
        for column in fields(self):
            view = np.asarray(getattr(self, column.name)).view()
            view.flags.writeable = False
            object.__setattr__(self, column.name, view)

    def __len__(self) -> int:
        return int(np.asarray(self.capture).shape[0])

    @classmethod
    def empty(cls) -> "Rows":
        return cls(
            capture=np.zeros(0, np.int64), page=np.zeros(0, np.int64),
            tile_code=np.zeros(0, np.int64), plane=np.zeros(0, np.int64),
            delta_dots_xy=np.zeros((0, 2), np.float64),
            measured_xy=np.zeros((0, 2), bool),
            weight=np.zeros(0, np.float64), source=np.zeros(0, np.int64),
            window=np.zeros(0, np.int64),
            pose_generation=np.zeros(0, np.int64))

    def select(self, keep: np.ndarray) -> "Rows":
        """The rows a boolean mask or an index array keeps.

        This is how the estimator cuts the table, and it cuts it per
        AXIS: a row that measured x alone is not evidence about y, so
        the two axes are two different sets of rows over the same page.
        """
        rows = np.asarray(keep)
        return Rows(**{name: np.asarray(getattr(self, name))[rows]
                       for name in COLUMNS})

    def sole_page(self) -> int | None:
        """The one page these rows speak about, or None when empty.

        A field is per (page, plane) and a solve is per page (I1), so a
        table that reached the estimator carrying two pages is a pooling
        defect upstream and not a case to be handled here.
        """
        pages = np.unique(np.asarray(self.page, np.int64))
        if pages.size > 1:
            raise ValueError(
                f"evidence: one page per solve, got {pages.tolist()}")
        return int(pages[0]) if pages.size else None

    @classmethod
    def concat(cls, *parts: "Rows") -> "Rows":
        if not parts:
            return cls.empty()
        return cls(**{
            name: np.concatenate([np.asarray(getattr(part, name))
                                  for part in parts])
            for name in COLUMNS})

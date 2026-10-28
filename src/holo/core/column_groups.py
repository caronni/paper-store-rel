"""Column groups — one pooled symbol width shared by streams of unequal
width (docs/CMY8-COLUMN-GROUPS.md; rulings 2026-09-04).

The pooled fountain (fountain.py) is GF(2)-column-separable, so its one
symbol width S can be cut into Z column groups and a narrower stream's
tile can carry a subset of them. This module is the LAW: the rational
partition, the ruled choice of Z, what each stream carries, and the
record of what one tile holds (``TileSlots``). holo3/format/fountain.py
carries the same law and slot map in holo3's docstring-free style
(without the planner-only ceilings), and holo3's tests pin its law table
and slot map against this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache


MAX_COLUMN_GROUPS = 32          # the ruled cap on solves per block (§3.9)


@dataclass(frozen=True)
class ColumnGroups:
    """How one pooled symbol width is shared by streams of unequal width
    (docs/CMY8-COLUMN-GROUPS.md).

    The pool is GF(2)-column-separable, so its symbol of ``symbol_bits``
    is cut into ``n_groups`` column groups by ``bounds`` — a rational
    partition, group widths within one bit of each other. A tile of
    stream ``s`` carries ``carried[s]`` CONSECUTIVE groups: every group
    when its stream is as wide as the symbol, fewer when it is narrower,
    with zero bits after the last one. Equal widths are the one-group
    case, where every tile carries the whole symbol and nothing below
    differs from fountain-v2.
    """

    widths: tuple[int, ...]        # per-stream symbol widths, bits
    bounds: tuple[int, ...]        # group g spans bits [bounds[g], bounds[g+1])
    carried: tuple[int, ...]       # groups per tile, per stream

    @classmethod
    def one(cls, widths: tuple[int, ...]) -> "ColumnGroups":
        """The one-group case of equal widths: every tile carries the
        whole symbol — fountain-v2 exactly."""
        widths = tuple(int(w) for w in widths)
        if len(set(widths)) != 1:
            raise ValueError(f"one group needs equal widths, got {widths}")
        return cls(widths, (0, widths[0]), (1,) * len(widths))

    @property
    def n_groups(self) -> int:
        return len(self.bounds) - 1

    @property
    def symbol_bits(self) -> int:
        return self.bounds[-1]

    @property
    def uniform(self) -> bool:
        return self.n_groups == 1

    def width(self, group: int) -> int:
        return self.bounds[group + 1] - self.bounds[group]

    @property
    def chunks_per_site(self) -> int:
        """Groups carried by one site across all its streams."""
        return sum(self.carried)

    def plane_tier_ceiling(self, dead: int) -> Fraction:
        """The dial up to which every block survives stream ``dead``
        dying with all pages present: every group keeps
        ``1 - carried[dead]/chunks_per_site`` of its equations."""
        n = self.chunks_per_site
        return Fraction(n - self.carried[dead], n)

    @property
    def any_plane_ceiling(self) -> Fraction:
        """The dead-plane tier's dial ceiling for ANY one dead stream —
        the heaviest stream binds ((n-1)/n at uniform widths)."""
        return min(self.plane_tier_ceiling(s)
                   for s in range(len(self.carried)))

    @property
    def spare_bits_per_site(self) -> Fraction:
        """Mean bits per site outside every carried group — the zero
        tails, which are capacity the row does not use."""
        z = self.n_groups
        return sum((Fraction(w * z - c * self.symbol_bits, z)
                    for w, c in zip(self.widths, self.carried)),
                   Fraction(0))


def _carried_groups(group_widths: tuple[int, ...], width: int) -> int:
    """Largest n such that EVERY cyclic window of n consecutive groups
    fits in ``width`` bits (a tile carries whichever window its chunk
    offset lands on)."""
    z = len(group_widths)
    prefix = [0]
    for w in group_widths + group_widths:
        prefix.append(prefix[-1] + w)
    for n in range(z, 0, -1):
        if max(prefix[i + n] - prefix[i] for i in range(z)) <= width:
            return n
    return 0


@lru_cache(maxsize=None)
def column_groups(widths: tuple[int, ...],
                  max_groups: int = MAX_COLUMN_GROUPS) -> ColumnGroups:
    """The ruled column grouping of these stream widths (ruling
    2026-09-04, docs/CMY8-COLUMN-GROUPS.md §3.9).

    Equal widths: one group. Otherwise the symbol is the widest stream's
    width S; for every Z in 2..max_groups the rational partition
    ``bounds[g] = floor(g*S/Z)`` is scored by the mean spare bits per
    site it leaves, and the smallest Z attaining the minimum wins. A
    stream carries the largest run of consecutive groups whose widest
    cyclic window fits its width; widths too narrow for one group at
    every Z refuse.
    """
    widths = tuple(int(w) for w in widths)
    if not widths or min(widths) < 1:
        raise ValueError("stream widths must be positive")
    s = max(widths)
    if len(set(widths)) == 1:
        return ColumnGroups.one(widths)
    best: ColumnGroups | None = None
    for z in range(2, max_groups + 1):
        bounds = tuple((g * s) // z for g in range(z + 1))
        group_widths = tuple(bounds[g + 1] - bounds[g] for g in range(z))
        carried = tuple(_carried_groups(group_widths, w) for w in widths)
        if min(carried) < 1:
            continue
        candidate = ColumnGroups(widths, bounds, carried)
        if (best is None
                or candidate.spare_bits_per_site < best.spare_bits_per_site):
            best = candidate
    if best is None:
        raise ValueError(f"no column grouping of up to {max_groups} groups "
                         f"fits stream widths {widths}")
    return best


@dataclass(frozen=True)
class TileSlots:
    """What one tile carries, slot by slot (``VolumeCode.tile_slots``).

    Slot ``i`` is tile symbol bits ``[edges[i], edges[i+1])`` and holds
    column group ``groups[i]`` of in-block source row ``source_rows[i]``
    — or, when ``source_rows[i] < 0``, of the tile's one ``repair_row``
    (an in-block row index >= K_b, the same numbering fountain-v2 uses).
    Bits past ``edges[-1]`` are zero. A one-group pool has one slot
    holding the whole symbol.
    """

    block: int
    groups: tuple[int, ...]
    source_rows: tuple[int, ...]
    repair_row: int | None
    edges: tuple[int, ...]

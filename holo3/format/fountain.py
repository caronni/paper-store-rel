from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

import numpy as np

from .keystream import (
    DOMAIN_BLOCK_ASSIGN,
    DOMAIN_COLOR_FOUNTAIN_ROW,
    DOMAIN_FOUNTAIN_ROW,
    blocks,
    color_block_assign_keys,
    keys64,
)

BLOCK_K_MAX = 16384
CHUNK_BITS = 1 << 24
_WORD = np.dtype("<u8")
_REVERSE_BYTE = np.asarray([
    int(f"{value:08b}"[::-1], 2) for value in range(256)
], np.uint8)


class FountainIntegrityError(ValueError):
    pass


def n_blocks_for(k_total: int) -> int:
    return -(-k_total // BLOCK_K_MAX)


MAX_COLUMN_GROUPS = 32


@dataclass(frozen=True)
class ColumnGroups:
    widths: tuple[int, ...]
    bounds: tuple[int, ...]
    carried: tuple[int, ...]

    @classmethod
    def one(cls, widths: tuple[int, ...]) -> "ColumnGroups":
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
    def spare_bits_per_site(self) -> Fraction:
        z = self.n_groups
        return sum((Fraction(w * z - c * self.symbol_bits, z)
                    for w, c in zip(self.widths, self.carried)),
                   Fraction(0))


def _carried_groups(group_widths: tuple[int, ...], width: int) -> int:
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
    block: int
    groups: tuple[int, ...]
    source_rows: tuple[int, ...]
    repair_row: int | None
    edges: tuple[int, ...]


@dataclass(frozen=True)
class BlockStatus:
    block: int
    needed: int
    have: int
    rows: int
    rank: int | None
    solved: bool
    groups_open: int
    n_groups: int
    min_rows: int

    @property
    def short(self) -> int:
        if self.solved:
            return 0
        known = self.rank if self.rank is not None else min(self.rows,
                                                            self.needed)
        return self.needed - known


def _pack_bits_2d(bits_2d: np.ndarray) -> np.ndarray:
    b = np.ascontiguousarray(np.asarray(bits_2d, np.uint8))
    r, l = b.shape
    words = -(-l // 64)
    pb = np.packbits(b, axis=1, bitorder="little")
    out = np.zeros((r, words * 8), np.uint8)
    out[:, :pb.shape[1]] = pb
    return out.view(_WORD)


def _unpack_bits_2d(packed: np.ndarray, n_bits: int) -> np.ndarray:
    return np.unpackbits(packed.view(np.uint8), axis=1, bitorder="little",
                         count=n_bits)


def _ge_solve_gf2(rows: np.ndarray, vals: np.ndarray, k: int
                  ) -> tuple[int, np.ndarray | None]:
    n_rows = rows.shape[0]
    pivot_of_col = np.full(k, -1, np.int64)
    rank = 0
    for col in range(k):
        if rank == n_rows:
            break
        w = col >> 6
        mask = np.uint64(1 << (col & 63))
        cand = np.flatnonzero(rows[rank:, w] & mask)
        if cand.size == 0:
            continue
        r = rank + int(cand[0])
        if r != rank:
            rows[[rank, r]] = rows[[r, rank]]
            vals[[rank, r]] = vals[[r, rank]]
        hit = np.flatnonzero(rows[:, w] & mask)
        hit = hit[hit != rank]
        if hit.size:
            rows[hit] ^= rows[rank]
            vals[hit] ^= vals[rank]
        pivot_of_col[col] = rank
        rank += 1
    if (pivot_of_col < 0).any():
        return rank, None
    return rank, vals[pivot_of_col]


def unpack_rows(packed_rows: np.ndarray, s_bits: int) -> np.ndarray:
    return np.unpackbits(np.atleast_2d(packed_rows), axis=1)[:, :s_bits]


class VolumeCode:

    def __init__(self, k_total: int, s_bits: int, seed: bytes,
                 tiles_per_page: int, *,
                 stream_id: str | None = None,
                 fountain_aux: int | None = None,
                 n_streams: int = 1,
                 groups: ColumnGroups | None = None) -> None:
        if stream_id is None:
            stream_aux = 0
            row_domain = DOMAIN_FOUNTAIN_ROW
        else:
            stream_aux = int(fountain_aux)
            row_domain = DOMAIN_COLOR_FOUNTAIN_ROW
        self.k_total = k_total
        self.s_bits = s_bits
        self.seed = seed
        self.tiles_per_page = tiles_per_page
        self.stream_id = stream_id
        self.stream_aux = int(stream_aux)
        self.n_streams = int(n_streams)
        self.symbols_per_page = tiles_per_page * self.n_streams
        self.fountain_row_domain = int(row_domain)
        self.n_blocks = n_blocks_for(k_total)
        base, rem = divmod(k_total, self.n_blocks)
        self.k_per_block: tuple[int, ...] = tuple(
            base + 1 if b < rem else base for b in range(self.n_blocks))
        self.block_offsets: tuple[int, ...] = tuple(
            int(x) for x in np.concatenate(
                ([0], np.cumsum(self.k_per_block)[:-1])))
        if groups is None:
            groups = ColumnGroups.one((s_bits,) * self.n_streams)
        elif (groups.symbol_bits != s_bits
              or len(groups.carried) != self.n_streams):
            raise ValueError("column groups disagree with the symbol width "
                             "or the stream count")
        self.groups = groups
        self._pages: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        zero = np.zeros(self.n_blocks, np.int64)
        self._cum: list[tuple[np.ndarray, np.ndarray]] = [(zero, zero)]
        self._systematic: dict[int, int] = {}

    def quotas(self, page: int, stream: int = 0) -> np.ndarray:
        t, b = self.tiles_per_page, self.n_blocks
        base, rem = divmod(t, b)
        q = np.full(b, base, dtype=np.int64)
        if rem:
            seg = page * self.n_streams + stream
            q[(np.arange(b) - seg) % b < rem] += 1
        return q

    def _cumulative(self, seg: int) -> tuple[np.ndarray, np.ndarray]:
        while len(self._cum) <= seg:
            prev = len(self._cum) - 1
            page, stream = divmod(prev, self.n_streams)
            quota = self.quotas(page, stream)
            tiles, chunks = self._cum[-1]
            self._cum.append((tiles + quota,
                              chunks + quota * self.groups.carried[stream]))
        return self._cum[seg]

    def page_assignment(self, page: int
                        ) -> tuple[np.ndarray, np.ndarray]:
        if page in self._pages:
            return self._pages[page]
        t, b, n = self.tiles_per_page, self.n_blocks, self.n_streams
        local = np.arange(t, dtype=np.int64)
        block_of = np.empty(t * n, dtype=np.int64)
        row_of = np.empty(t * n, dtype=np.int64)
        for stream in range(n):
            if self.stream_id is None:
                keys = keys64(
                    self.seed,
                    DOMAIN_BLOCK_ASSIGN,
                    0,
                    page,
                    local * n + stream,
                    0,
                )
            else:
                keys = color_block_assign_keys(
                    self.seed,
                    self.stream_aux,
                    page,
                    local,
                )
            order = np.argsort(keys, kind="stable")
            seg_block = np.empty(t, dtype=np.int64)
            quota = self.quotas(page, stream)
            seg_block[order] = np.repeat(np.arange(b, dtype=np.int64),
                                         quota)
            seg_row = np.empty(t, dtype=np.int64)
            cum = self._cumulative(page * n + stream)[0]
            starts = np.concatenate(([0], np.cumsum(quota)))
            for blk in range(b):
                idx = (np.flatnonzero(seg_block == blk)
                       if self.groups.uniform
                       else order[starts[blk]:starts[blk + 1]])
                seg_row[idx] = cum[blk] + np.arange(idx.size,
                                                    dtype=np.int64)
            block_of[stream::n] = seg_block
            row_of[stream::n] = seg_row
        self._pages[page] = (block_of, row_of)
        return self._pages[page]

    def block_row_of(self, esi: int) -> tuple[int, int]:
        page, local = divmod(esi, self.symbols_per_page)
        block_of, row_of = self.page_assignment(page)
        return int(block_of[local]), int(row_of[local])

    def systematic_positions(self, block: int) -> int:
        n_sys = self._systematic.get(block)
        if n_sys is None:
            target = self.k_per_block[block] * self.groups.n_groups
            seg = 0
            while self._cumulative(seg + 1)[1][block] < target:
                seg += 1
            page, stream = divmod(seg, self.n_streams)
            per_tile = self.groups.carried[stream]
            tiles, chunks = self._cumulative(seg)
            before = int(chunks[block])
            n_sys = int(tiles[block]) + min(
                int(self.quotas(page, stream)[block]),
                -(-(target - before) // per_tile))
            self._systematic[block] = n_sys
        return n_sys

    def tile_slots(self, esi: int) -> TileSlots:
        block, position = self.block_row_of(esi)
        stream = esi % self.n_streams
        seg = esi // self.symbols_per_page * self.n_streams + stream
        per_tile = self.groups.carried[stream]
        z = self.groups.n_groups
        kb = self.k_per_block[block]
        tiles, chunks = self._cumulative(seg)
        chunk = int(chunks[block]) + (position - int(tiles[block])) * per_tile
        target = kb * z
        repair_row = (None if chunk < target
                      else kb + position - self.systematic_positions(block))
        groups: list[int] = []
        source_rows: list[int] = []
        edges = [0]
        for c in range(chunk, chunk + per_tile):
            if c >= target and repair_row is None:
                break
            g = c % z
            groups.append(g)
            source_rows.append(c // z if c < target else -1)
            edges.append(edges[-1] + self.groups.width(g))
        return TileSlots(block, tuple(groups), tuple(source_rows),
                         repair_row, tuple(edges))


class Decoder:

    def __init__(self, code: VolumeCode) -> None:
        self.code = code
        self._symbols: dict[int, np.ndarray] = {}
        self._items: dict[tuple[int, int], list[tuple[int, int, int, int]]] = {
            (b, g): []
            for b in range(code.n_blocks)
            for g in range(code.groups.n_groups)}
        self._solved: dict[tuple[int, int], np.ndarray] = {}
        self._rank: dict[tuple[int, int], int] = {}
        self._tried_at: dict[tuple[int, int], int] = {}
        self._have = np.zeros(code.n_blocks, np.int64)

    def add_symbol(self, esi: int, symbol_bits: np.ndarray) -> bool:
        esi = int(esi)
        v = np.asarray(symbol_bits, np.uint8).ravel()
        width = self.code.groups.widths[esi % self.code.n_streams]
        if v.size != width:
            raise FountainIntegrityError(
                f"symbol at ESI {esi} has {v.size} bits; its stream "
                f"carries {width}")
        packed = np.packbits(v)
        if esi in self._symbols:
            if np.array_equal(self._symbols[esi], packed):
                return False
            raise FountainIntegrityError(
                f"conflicting certified values at ESI {esi}")
        tile = self.code.tile_slots(esi)
        self._symbols[esi] = packed
        self._have[tile.block] += 1
        for g, r, lo, hi in zip(tile.groups, tile.source_rows, tile.edges,
                                tile.edges[1:]):
            key = (tile.block, g)
            if key not in self._solved:
                row = r if r >= 0 else tile.repair_row
                self._items[key].append((row, esi, lo, hi))
                self._rank.pop(key, None)
        return True

    def _packed_generator_rows(
            self, block: int,
            items: list[tuple[int, int, int, int]]) -> np.ndarray:
        kb = self.code.k_per_block[block]
        words = -(-kb // 64)
        raw = np.zeros((len(items), words * 8), dtype=np.uint8)
        repair_positions: list[int] = []
        repair_rows: list[int] = []
        for n, (row, *_slot) in enumerate(items):
            if row < kb:
                raw[n, row >> 3] |= np.uint8(1 << (row & 7))
            else:
                repair_positions.append(n)
                repair_rows.append(row)
        if repair_rows:
            n_draws = -(-kb // 128)
            rows = np.asarray(repair_rows, np.int64)
            row_domain, stream_aux = (
                (DOMAIN_FOUNTAIN_ROW, 0)
                if self.code.stream_id is None
                else (
                    self.code.fountain_row_domain,
                    self.code.stream_aux,
                )
            )
            encrypted = blocks(
                self.code.seed,
                row_domain,
                stream_aux,
                block,
                np.repeat(rows, n_draws),
                np.tile(np.arange(n_draws, dtype=np.int64), rows.size),
            ).reshape(rows.size, n_draws * 16)
            n_bytes = -(-kb // 8)
            selected = np.asarray(repair_positions, np.intp)
            raw[selected, :n_bytes] = _REVERSE_BYTE[
                encrypted[:, :n_bytes]]
            if kb & 7:
                raw[selected, n_bytes - 1] &= np.uint8((1 << (kb & 7)) - 1)
        return raw.view(_WORD)

    def _unpacked(self, esi: int, cache: dict[int, np.ndarray]) -> np.ndarray:
        bits = cache.get(esi)
        if bits is None:
            width = self.code.groups.widths[esi % self.code.n_streams]
            bits = cache[esi] = unpack_rows(self._symbols[esi], width)[0]
        return bits

    def _solve_group(self, block: int, group: int,
                     items: list[tuple[int, int, int, int]],
                     cache: dict[int, np.ndarray]
                     ) -> tuple[int, np.ndarray | None]:
        kb = self.code.k_per_block[block]
        src = {row: (esi, lo, hi) for row, esi, lo, hi in items if row < kb}
        if len(src) == kb:
            return kb, np.stack([self._unpacked(esi, cache)[lo:hi]
                                 for esi, lo, hi in map(src.__getitem__,
                                                        range(kb))])
        rows = self._packed_generator_rows(block, items)
        vals = _pack_bits_2d(np.stack(
            [self._unpacked(esi, cache)[lo:hi] for _row, esi, lo, hi in items]))
        rank, solved_p = _ge_solve_gf2(rows, vals, kb)
        if solved_p is None:
            return rank, None
        return rank, _unpack_bits_2d(solved_p, self.code.groups.width(group))

    def try_solve(self) -> np.ndarray | None:
        z = self.code.groups.n_groups
        cache: dict[int, np.ndarray] = {}
        for b in range(self.code.n_blocks):
            for g in range(z):
                key = (b, g)
                items = self._items[key]
                if (key in self._solved
                        or len(items) < self.code.k_per_block[b]
                        or self._tried_at.get(key) == len(items)):
                    continue
                rank, solved = self._solve_group(b, g, sorted(items), cache)
                if solved is None:
                    self._rank[key] = rank
                    self._tried_at[key] = len(items)
                else:
                    self._solved[key] = solved
                    self._rank.pop(key, None)
                    self._tried_at.pop(key, None)
                    self._items[key] = []
        if len(self._solved) < self.code.n_blocks * z:
            return None
        out = np.zeros((self.code.k_total, self.code.s_bits), np.uint8)
        bounds = self.code.groups.bounds
        for (b, g), solved in self._solved.items():
            off = self.code.block_offsets[b]
            out[off:off + self.code.k_per_block[b],
                bounds[g]:bounds[g + 1]] = solved
        return out

    def block_status(self) -> tuple[BlockStatus, ...]:
        z = self.code.groups.n_groups
        out = []
        for b in range(self.code.n_blocks):
            kb = self.code.k_per_block[b]
            have = int(self._have[b])
            open_keys = [(b, g) for g in range(z) if (b, g) not in self._solved]
            if not open_keys:
                out.append(BlockStatus(b, kb, have, kb, kb, True, 0, z, kb))
                continue
            scarcest = max(open_keys, key=lambda key: kb - self._rank.get(
                key, min(len(self._items[key]), kb)))
            out.append(BlockStatus(b, kb, have, len(self._items[scarcest]),
                                   self._rank.get(scarcest), False,
                                   len(open_keys), z,
                                   min(len(self._items[key])
                                       for key in open_keys)))
        return tuple(out)

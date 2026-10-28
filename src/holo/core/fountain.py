"""fountain-v2 core — systematic dense random-linear fountain over GF(2).

HOLO-DESIGN §7.2 (format decision F8, revised per the 2026-07-19 external
review's occupancy finding). The GF(2) coding core (bit-packed
Gauss-Jordan, systematic fast path, balanced first-blocks-+1 split) is
carried from the measured fountain-v1 record (e015/e016, paperholo);
the BLOCK ASSIGNMENT is new: fountain-v1's `block = ESI mod B` aliased
against page rasters, so exact-q spatial crops starved blocks and the
"any q of tiles" promise was false for every multi-block volume
(measured: 16/32 blocks starved by a half-page column crop at q=0.5).
All physical volumes to date were single-block and unaffected.

FROZEN DERIVATION (fountain-v2; precise enough to reimplement):

  K source symbols of S bits. n_blocks B = ceil(K / 16384) (BLOCK_K_MAX;
  GE at 16384 is ~1 min/block — the feasibility knee). Balanced split:
  K_b = K // B + 1 for the FIRST (K mod B) blocks. Source data maps to
  blocks CONTIGUOUSLY: block b owns global source rows
  [offset_b, offset_b + K_b), offset_b = sum of earlier K_b.

  BLOCK ASSIGNMENT (per-page exact quotas + keystream shuffle). ESI = the
  global tile counter; page p = ESI // tiles_per_page, local tile
  i = ESI % tiles_per_page, T = tiles_per_page:
    quota_b(p) = T // B  +  (1 if (b - p) mod B < T mod B else 0)
    keys      = 64-bit big-endian sort key per local tile
                (DOMAIN_BLOCK_ASSIGN, aux=0, major=p, u=i, v=0,
                 block bytes 0..7); order = argsort(keys), ties by i
    the sorted tiles receive the block list
                [0]*quota_0(p) ++ [1]*quota_1(p) ++ ... (ascending b)
  Within (page, block), tiles ordered by ASCENDING local index receive
  consecutive in-block rows starting at the block's cumulative quota over
  all earlier pages. Rows r < K_b are SOURCE (identity: block column r);
  rows r >= K_b are repair — defined for every larger row, so appending
  pages stays rateless AND, because every page carries every block's
  quota, added pages provably add repair to ALL blocks uniformly.
  Every exact quota makes whole-page loss remove proportional amounts of
  each block (deterministic promise tier); sub-page crops concentrate
  hypergeometrically with no raster aliasing (probabilistic tier).

  Repair coefficients (packed bulk draw, keystream domain table):
  coefficient c of (block b, row r) = bit (c % 128), MSB-first, of the
  AES block at (DOMAIN_FOUNTAIN_ROW, aux=0, major=b, u=r, v=c // 128) —
  dense, ~K_b/2 expected weight.

  Decoding. Per block: systematic fast path when all K_b source rows are
  present; else bit-packed Gauss-Jordan over GF(2) (columns packed 64 per
  uint64 word, little bit order — internal solver packing only, never
  format surface), attempted only when the block holds at
  least K_b symbols. Dense-RLF overhead is provable:
  P(block unsolvable) <= 2^-delta at K_b + delta received.

POOLED MULTISTREAM EXTENSION (the -v1 colour rows; design + adopted
rulings: docs/CMY8-POOLED-FOUNTAIN.md §2, 2026-08-13). A pooled row runs
ONE fountain over every stream's symbols: symbol index
``esi = counter*n_streams + stream_idx`` (stream order = the row's
declared stream ids), so one page carries ``T*n_streams`` symbols. The
assignment generalizes STREAM-EXACTLY and reduces bit-identically at
``n_streams = 1`` (the format-fork guard):

  quota_b(p, s) = T//B + (1 if (b - (p*n + s)) mod B < T mod B else 0)
  keys: DOMAIN_BLOCK_ASSIGN with u = local_tile*n + s, argsort WITHIN
        each stream's T keys (ties by local tile);
  row_of: within (page, stream, block), ascending local tile receives
        consecutive in-block rows starting at the block's cumulative
        quota over all earlier (page, stream) pairs, ascending (p, s).

Repair coefficients ride DOMAIN_FOUNTAIN_ROW exactly like K. One dead
stream therefore removes EXACTLY its quota from every block — plane loss
is a deterministic promise tier. Rotation balance is a per-block totals
property, not a per-stream fairness claim (when n divides B the extras
concentrate on aligned (page, stream) pairs; every tier carries the
T//B floor, so this is harmless). Pooled capacity is promise-grade over
THREE tiers (``pooled_page_capacity_sufficient``); whether the plane
tier participates is the CALLER's dial policy (``enforce_plane_tier``,
decided in gen.plan), never predicate arithmetic — tier 3's budget grows
with the page count, so enforcing it above q = (n-1)/n would only
inflate pages at ~(n-1)/n fill instead of honoring the dial.

COLUMN-GROUP EXTENSION (uneven rung triplets under one pool; design +
rulings 2026-09-04: docs/CMY8-COLUMN-GROUPS.md). The pool is GF(2)-
column-separable, so ONE symbol width S can be shared by streams of
unequal width: ``column_groups`` cuts S into Z column groups (a rational
partition, widths within one bit) and a tile of stream s carries
``carried[s]`` CONSECUTIVE groups. Chunks (= groups) fill a block's
tiles consecutively in the block's fill order, so a narrow stream's
groups rotate by consecutive residues; source chunk c of a block is
group c mod Z of in-block source row c // Z, a tile past the block's
K_b*Z source chunks carries ONE repair row (K_b + its rank among the
block's repair tiles) over its groups, and a tile straddling that
boundary carries its source chunks and zero bits after them. Fill
order within (page, stream, block): the frozen ASCENDING local index at
uniform widths, the DOMAIN_BLOCK_ASSIGN key order otherwise (spatial
whiteness for the rotation). Uniform widths are the one-group case and
reproduce every rule above bit for bit — the format-fork guard.

The column-group LAW lives in column_groups.py and the promise-grade
capacity arithmetic (reserve, budgets, the page and dead-plane tiers) in
capacity.py; this module is the code, its encoder, and the one-group
decoder (a column-group code is decoded by holo3).

Certified-conflict rule (HOLO-DESIGN §6.3): two different values at one
ESI mean mixed sheets or an upstream fault — Decoder.add_symbol raises
FountainIntegrityError, never silently keeps either.
"""
from __future__ import annotations

import operator

import numpy as np

from .column_groups import ColumnGroups, TileSlots
from .keystream import (
    COLOR_STREAM_AUX,
    DOMAIN_BLOCK_ASSIGN,
    DOMAIN_COLOR_BLOCK_ASSIGN,
    DOMAIN_COLOR_FOUNTAIN_ROW,
    DOMAIN_FOUNTAIN_ROW,
    blocks,
    color_block_assign_keys,
    color_fountain_rows_bits,
    fountain_rows_bits,
    keys64,
)

FOUNTAIN_VERSION = "fountain-v2"
BLOCK_K_MAX = 16384             # max source symbols per fountain block
_WORD = np.dtype("<u8")         # GE-core packing word — INTERNAL ONLY
_REVERSE_BYTE = np.asarray([
    int(f"{value:08b}"[::-1], 2) for value in range(256)
], np.uint8)
# (_pack/_unpack are a symmetric in-process pair; their bit order never
# crosses an API and is NOT format surface — the format-wide bit order
# is MSB-first, §13.12. Explicit dtype = cross-platform determinism.)


class FountainIntegrityError(ValueError):
    """Conflicting certified symbol values at one ESI (sheet mixing)."""


# --------------------------------------------------------------- blocks

def n_blocks_for(k_total: int) -> int:
    """ceil(k_total / BLOCK_K_MAX); 0 for k_total == 0."""
    if k_total < 0:
        raise ValueError("k_total must be >= 0")
    return -(-k_total // BLOCK_K_MAX)


def validated_count(value: int, what: str) -> int:
    """A positive integer count (streams, solves per block), or a typed
    refusal naming what was expected."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, np.integer)):
        raise TypeError(f"{what} must be an integer")
    if int(value) < 1:
        raise ValueError(f"{what} must be >= 1")
    return int(value)




# ------------------------------------- bit packing + GF(2) Gauss-Jordan

def _pack_bits_2d(bits_2d: np.ndarray) -> np.ndarray:
    """(R, L) {0,1} uint8 -> (R, ceil(L/64)) uint64: column c = bit (c & 63)
    of word (c >> 6), little bit order (internal GE packing — see the
    _WORD note; inverted only by _unpack_bits_2d, never format-visible)."""
    b = np.ascontiguousarray(np.asarray(bits_2d, np.uint8))
    if b.ndim != 2:
        raise ValueError("expected a 2-D bit array")
    r, l = b.shape
    words = -(-l // 64)
    pb = np.packbits(b, axis=1, bitorder="little")
    out = np.zeros((r, words * 8), np.uint8)
    out[:, :pb.shape[1]] = pb
    return out.view(_WORD)


def _unpack_bits_2d(packed: np.ndarray, n_bits: int) -> np.ndarray:
    """Inverse of _pack_bits_2d -> (R, n_bits) uint8."""
    return np.unpackbits(packed.view(np.uint8), axis=1, bitorder="little",
                         count=n_bits)


def _ge_solve_gf2(rows: np.ndarray, vals: np.ndarray, k: int
                  ) -> tuple[int, np.ndarray | None]:
    """In-place Gauss-Jordan over GF(2). rows (R, ceil(k/64)) uint64 packed
    generator rows; vals (R, Wv) uint64 packed symbol values, XORed
    alongside. Column-order partial pivot (first available row) —
    deterministic. Returns (rank, solved): solved is (k, Wv) packed source
    values (row j = in-block source j) when rank == k, else None."""
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
    # full reduction: pivot rows are unit vectors -> vals ARE the sources
    return rank, vals[pivot_of_col]


# ---------------------------------------------------------- source store

# Bounded temporary-memory footing for the bit packer: unpack at most about
# 16 Mbit per chunk, never a payload-sized bit vector.
CHUNK_BITS = 1 << 24


def pack_bit_slice(data: np.ndarray, content_bits: int, bit_start: int,
                   k_total: int, s_bits: int) -> np.ndarray:
    """Pack one zero-extended flat-bit slice into row-packed source rows.

    The format-axis mapping shared by single-stream volumes (pack_source)
    and the CMY8 stream-major split (format.streamset): rows are MSB-first
    packings of bits [bit_start + j*S, bit_start + (j+1)*S) of ``data``,
    zero-padded past ``content_bits``.
    """
    row_bytes = -(-s_bits // 8)
    out = np.zeros((k_total, row_bytes), dtype=np.uint8)
    chunk_rows = max(1, CHUNK_BITS // s_bits)

    for row0 in range(0, k_total, chunk_rows):
        row1 = min(row0 + chunk_rows, k_total)
        slice_lo = bit_start + row0 * s_bits
        if slice_lo >= content_bits:
            break
        slice_hi = min(
            bit_start + row1 * s_bits,
            bit_start + k_total * s_bits,
            content_bits,
        )
        byte_lo = slice_lo // 8
        byte_hi = -(-slice_hi // 8)
        unpacked = np.unpackbits(
            data[byte_lo:byte_hi], bitorder="big"
        )
        source_offset = slice_lo - byte_lo * 8
        available = slice_hi - slice_lo
        segment = np.zeros((row1 - row0) * s_bits, dtype=np.uint8)
        segment[:available] = unpacked[
            source_offset:source_offset + available
        ]
        out[row0:row1] = np.packbits(
            segment.reshape(row1 - row0, s_bits),
            axis=1,
            bitorder="big",
        )
    return out


def pack_source(stream: bytes, k_total: int, s_bits: int) -> np.ndarray:
    """The padded envelope stream as row-packed source symbols:
    (k_total, ceil(s_bits/8)) uint8, row j = MSB-first packing of stream
    bits [j*S, (j+1)*S). Built in bounded chunks; bits beyond the stream
    are zero padding."""
    if len(stream) * 8 > k_total * s_bits:
        raise ValueError("stream longer than K*S bits")
    return pack_bit_slice(
        np.frombuffer(stream, dtype=np.uint8),
        len(stream) * 8, 0, k_total, s_bits,
    )


def unpack_rows(packed_rows: np.ndarray, s_bits: int) -> np.ndarray:
    """Row-packed (R, ceil(S/8)) -> (R, S) uint8 bits (MSB-first rows)."""
    return np.unpackbits(np.atleast_2d(packed_rows), axis=1)[:, :s_bits]


# ------------------------------------------------------------------ code

class VolumeCode:
    """One volume's fountain code: K source symbols of S bits under one
    volume seed, laid out over pages of tiles_per_page tiles. Pure coding
    theory + the frozen block-assignment derivation — no page geometry
    beyond the tile count."""

    def __init__(self, k_total: int, s_bits: int, seed: bytes,
                 tiles_per_page: int, *,
                 stream_id: str | None = None,
                 fountain_aux: int | None = None,
                 n_streams: int = 1,
                 groups: ColumnGroups | None = None) -> None:
        if k_total < 1:
            raise ValueError("k_total must be >= 1")
        if s_bits < 1:
            raise ValueError("s_bits must be >= 1")
        if not isinstance(seed, bytes) or not seed:
            raise ValueError("seed must be non-empty bytes")
        if tiles_per_page < 1:
            raise ValueError("tiles_per_page must be >= 1")
        n_streams = validated_count(n_streams, "n_streams")
        if n_streams > 1 and (stream_id is not None
                              or fountain_aux is not None):
            # Pooled rows run ONE fountain over all streams' symbols on
            # the K domains; the -v0 per-stream color path is a separate,
            # frozen construction (domains 14/15) and never pools.
            raise ValueError(
                "a pooled VolumeCode (n_streams > 1) is keyed like K; "
                "stream_id/fountain_aux belong to the -v0 per-stream path")
        if stream_id is None and fountain_aux is None:
            stream_aux = 0
            row_domain = DOMAIN_FOUNTAIN_ROW
            assign_domain = DOMAIN_BLOCK_ASSIGN
        elif stream_id is not None and fountain_aux is not None:
            try:
                expected_aux = COLOR_STREAM_AUX[stream_id]
            except (KeyError, TypeError):
                raise ValueError(
                    f"unknown color fountain stream {stream_id!r}; "
                    f"known: {tuple(COLOR_STREAM_AUX)}") from None
            if isinstance(fountain_aux, bool) or not isinstance(
                    fountain_aux, (int, np.integer)):
                raise TypeError("color fountain_aux must be an integer")
            if int(fountain_aux) != expected_aux:
                raise ValueError(
                    f"{stream_id}: fountain_aux must be {expected_aux}")
            stream_aux = expected_aux
            row_domain = DOMAIN_COLOR_FOUNTAIN_ROW
            assign_domain = DOMAIN_COLOR_BLOCK_ASSIGN
        else:
            raise ValueError(
                "color VolumeCode requires both stream_id and "
                "fountain_aux; K requires neither")
        self.k_total = k_total
        self.s_bits = s_bits
        self.seed = seed
        self.tiles_per_page = tiles_per_page
        self.stream_id = stream_id
        self.stream_aux = int(stream_aux)
        self.n_streams = int(n_streams)
        self.symbols_per_page = tiles_per_page * self.n_streams
        self.fountain_row_domain = int(row_domain)
        self.block_assign_domain = int(assign_domain)
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
        """(B,) per-block quota of one (page, stream) segment (sums to T).

        The remainder rotates over the flattened ``page*n_streams +
        stream`` index; at n_streams = 1 this is the frozen fountain-v2
        ``(b - page) mod B`` rule, bit-identical.
        """
        if not 0 <= stream < self.n_streams:
            raise ValueError("stream out of range for this code")
        t, b = self.tiles_per_page, self.n_blocks
        base, rem = divmod(t, b)
        q = np.full(b, base, dtype=np.int64)
        if rem:
            seg = page * self.n_streams + stream
            q[(np.arange(b) - seg) % b < rem] += 1
        return q

    def _cumulative(self, seg: int) -> tuple[np.ndarray, np.ndarray]:
        """Per block, the (tiles, chunks) of all (page, stream) segments
        < seg — the tile quotas, and the same quotas weighted by each
        stream's groups per tile (equal at one group)."""
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
        """(block_of, row_of), each (symbols_per_page,), cached.

        block_of: keystream-shuffled exact per-(page, stream) quotas,
        indexed by the page-local symbol ``u = local_tile*n_streams +
        stream``; row_of: within (page, stream, block), tiles receive
        consecutive in-block positions starting at the block's
        cumulative quota over all earlier (page, stream) segments — in
        ASCENDING LOCAL TILE INDEX for a one-group pool (the frozen
        fountain-v2 rule; at n_streams = 1 both arrays are bit-identical
        to it, u = local tile index), in the block-assignment KEY order
        for a column-group pool (so the narrow streams' rotating groups
        are spatially white, docs/CMY8-COLUMN-GROUPS.md §3.3).
        """
        if page < 0:
            raise ValueError("page must be >= 0")
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
                    self.stream_id,
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
        """ESI (page-local symbol space) -> (block, in-block position) —
        the source or repair row itself for a one-group pool; a
        column-group tile's rows come from ``tile_slots``.

        For single-stream codes the ESI is the global tile counter; for a
        pooled code it is ``counter*n_streams + stream_idx``.
        """
        if esi < 0:
            raise ValueError("esi must be >= 0")
        page, local = divmod(esi, self.symbols_per_page)
        block_of, row_of = self.page_assignment(page)
        return int(block_of[local]), int(row_of[local])

    def _require_one_group(self, what: str) -> None:
        if not self.groups.uniform:
            raise ValueError(f"{what} describes a one-group symbol; a "
                             f"column-group tile carries several rows — "
                             f"use tile_slots")

    def source_row_of(self, esi: int) -> int | None:
        """Global source-row index carried verbatim at this ESI, or None
        when the ESI is a repair symbol (one-group pools)."""
        self._require_one_group("source_row_of")
        b, r = self.block_row_of(esi)
        if r < self.k_per_block[b]:
            return self.block_offsets[b] + r
        return None

    def generator_row(self, esi: int) -> np.ndarray:
        """(K_b,) uint8 GF(2) generator row of the symbol at this ESI:
        unit e_r for source rows, packed-keystream dense repair row
        otherwise (defined for every larger row — rateless; one-group
        pools)."""
        self._require_one_group("generator_row")
        b, r = self.block_row_of(esi)
        kb = self.k_per_block[b]
        if r < kb:
            row = np.zeros(kb, np.uint8)
            row[r] = 1
            return row
        if self.stream_id is None:
            return fountain_rows_bits(self.seed, b, [r], kb)[0]
        return color_fountain_rows_bits(
            self.seed, self.stream_id, b, [r], kb)[0]

    def systematic_positions(self, block: int) -> int:
        """Positions of ``block`` (in fill order) whose first chunk is a
        source chunk; the positions after them carry repair rows. K_b
        for a one-group pool."""
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
        """What the tile at ``esi`` carries, group by group.

        Its stream's ``carried`` consecutive groups start at the tile's
        chunk offset — the chunks of every earlier position of its
        block, in fill order. Chunks below the block's ``K_b*Z`` are
        source chunks (group c mod Z of in-block source row c // Z);
        a tile starting beyond them carries one repair row, ``K_b`` plus
        its rank among the block's repair tiles; a tile straddling the
        boundary carries its source chunks and zero bits after them
        (ruling 2026-09-04). A one-group pool yields one slot holding
        the whole symbol at the row ``block_row_of`` reports.
        """
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

    def encode_symbols(self, source_packed: np.ndarray,
                       esis: np.ndarray) -> np.ndarray:
        """Symbol values for the given ESIs -> (len(esis), S) uint8 bits.

        source_packed is the row-packed (k_total, ceil(S/8)) source matrix
        from pack_source(). Each tile's slots (``tile_slots``) are filled
        left to right: source slots unpack their row, repair slots XOR
        the row-packed source rows selected by the packed coefficient
        draw — packing commutes with XOR, so no unpacked source matrix
        ever exists — and bits past the last slot are zero. A one-group
        pool fills the whole symbol; a narrower stream's tile is left-
        aligned, and the caller keeps its stream's width of it.
        """
        src = np.asarray(source_packed, np.uint8)
        row_bytes = -(-self.s_bits // 8)
        if src.shape != (self.k_total, row_bytes):
            raise ValueError(f"source_packed shape {src.shape} != "
                             f"({self.k_total}, {row_bytes})")
        es = np.asarray(esis, dtype=np.int64).ravel()
        if es.size and int(es.min()) < 0:
            raise ValueError("esis must be >= 0")
        out = np.zeros((es.size, self.s_bits), np.uint8)
        for n, e in enumerate(es):
            tile = self.tile_slots(int(e))
            off = self.block_offsets[tile.block]
            if tile.repair_row is None:
                rows = {r: unpack_rows(src[off + r], self.s_bits)[0]
                        for r in set(tile.source_rows)}
            else:
                kb = self.k_per_block[tile.block]
                coefficients = (
                    fountain_rows_bits(self.seed, tile.block,
                                       [tile.repair_row], kb)[0]
                    if self.stream_id is None
                    else color_fountain_rows_bits(
                        self.seed, self.stream_id, tile.block,
                        [tile.repair_row], kb)[0]
                )
                sel = np.flatnonzero(coefficients)
                if sel.size == 0:            # possible, vanishingly rare
                    continue
                acc = np.bitwise_xor.reduce(src[off + sel], axis=0)
                rows = {-1: unpack_rows(acc, self.s_bits)[0]}
            for g, r, lo, hi in zip(tile.groups, tile.source_rows,
                                    tile.edges, tile.edges[1:]):
                out[n, lo:hi] = rows[r][self.groups.bounds[g]:
                                        self.groups.bounds[g + 1]]
        return out


# --------------------------------------------------------------- decoder

class Decoder:
    """Per-block incremental fountain decoder over one VolumeCode.

    add_symbol collects (esi, value) pairs; values are certified upstream
    (LDPC+CRC), so a DIFFERENT value at an already-seen ESI is mixed
    sheets or an upstream fault and raises FountainIntegrityError —
    never first-wins. try_solve runs the per-block systematic fast path /
    packed GE; blocks below K_b symbols are skipped (elimination cannot
    succeed); solved blocks are cached; unsolved blocks re-attempt only
    when new symbols arrived.
    """

    def __init__(self, code: VolumeCode) -> None:
        if not code.groups.uniform:
            raise ValueError(
                "this decoder solves one-group codes; a column-group code's "
                "tiles carry several rows each and are decoded by holo3 "
                "(docs/CMY8-COLUMN-GROUPS.md)")
        self.code = code
        self._symbols: dict[int, np.ndarray] = {}     # esi -> packed row
        self._solved: dict[int, np.ndarray] = {}      # block -> (K_b, S)
        self._failed_at: dict[int, int] = {}          # block -> have count
        self._have = np.zeros(code.n_blocks, np.int64)
        # Rank is derived lazily during a solve/diagnostic close, never while
        # merely ingesting a still-incomplete certificate set.
        self._rank_cache: dict[int, tuple[int, int]] = {}

    def add_symbol(self, esi: int, symbol_bits: np.ndarray) -> bool:
        """Add one symbol value. Returns True when stored, False on an
        identical duplicate; raises FountainIntegrityError on a
        conflicting duplicate."""
        if isinstance(esi, (bool, np.bool_)):
            raise TypeError("esi must be an integer")
        try:
            esi = operator.index(esi)
        except TypeError as exc:
            raise TypeError("esi must be an integer") from exc
        if esi < 0:
            raise ValueError("esi must be >= 0")
        v = np.asarray(symbol_bits, np.uint8).ravel()
        if v.size != self.code.s_bits:
            raise ValueError(f"symbol has {v.size} bits, "
                             f"S = {self.code.s_bits}")
        if (v > 1).any():
            raise ValueError("symbol bits must be 0/1")
        packed = np.packbits(v)
        if esi in self._symbols:
            if np.array_equal(self._symbols[esi], packed):
                return False
            raise FountainIntegrityError(
                f"conflicting certified values at ESI {esi} — "
                f"mixed sheets or upstream fault")
        block, _row = self.code.block_row_of(esi)
        self._symbols[esi] = packed
        self._have[block] += 1
        self._rank_cache.pop(block, None)
        return True

    def _symbol_bits(self, esi: int) -> np.ndarray:
        return unpack_rows(self._symbols[esi], self.code.s_bits)[0]

    def _block_items(self) -> dict[int, list[tuple[int, int]]]:
        """block -> [(in-block row, esi)] ascending row (deterministic
        GE input order)."""
        buckets: dict[int, list[tuple[int, int]]] = {
            b: [] for b in range(self.code.n_blocks)}
        pairs = [(esi, self.code.block_row_of(esi))
                 for esi in sorted(self._symbols)]
        for esi, (b, r) in pairs:
            buckets[b].append((r, esi))
        for b in buckets:
            buckets[b].sort()
        return buckets

    def _packed_generator_rows(
            self, items: list[tuple[int, int]]) -> np.ndarray:
        """Generator rows for ``(in-block row, ESI)`` pairs, packed.

        Building an unpacked ``R x K_b`` stack can transiently cost 256 MiB
        at the declared 16,384-row block knee.  Fill the packed matrix
        directly; systematic rows need no generator allocation at all.
        """
        if not items:
            raise ValueError("cannot pack an empty generator-row set")
        block, _ = self.code.block_row_of(items[0][1])
        kb = self.code.k_per_block[block]
        words = -(-kb // 64)
        raw = np.zeros((len(items), words * 8), dtype=np.uint8)
        repair_positions: list[int] = []
        repair_rows: list[int] = []
        for n, (row, esi) in enumerate(items):
            item_block, expected_row = self.code.block_row_of(esi)
            if item_block != block or expected_row != row:
                raise ValueError("generator item does not match its ESI")
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

    def _exact_rank(self, block: int,
                    items: list[tuple[int, int]]) -> int:
        have = len(items)
        if have != int(self._have[block]):
            raise RuntimeError("fountain rank accounting lost a symbol")
        needed = self.code.k_per_block[block]
        if block in self._solved:
            return needed
        cached = self._rank_cache.get(block)
        if cached is not None and cached[0] == have:
            return cached[1]
        if not items:
            rank = 0
        elif sum(row < needed for row, _esi in items) == needed:
            rank = needed
        else:
            rows = self._packed_generator_rows(items)
            rank, _ = _ge_solve_gf2(
                rows, np.zeros((have, 1), dtype=_WORD), needed)
        self._rank_cache[block] = (have, int(rank))
        return int(rank)

    def rank_status(self) -> list[dict]:
        """Exact per-block rank accounting.

        Returns ``{block, needed, have, rank, rank_shortfall, solved}``.
        A solve caches the rank it already computed.  Otherwise this performs
        one coefficient-only elimination per changed block, matching the
        historical close-time work without penalizing every ingestion barrier.
        """
        buckets = self._block_items()
        result = []
        for block in range(self.code.n_blocks):
            needed = self.code.k_per_block[block]
            rank = self._exact_rank(block, buckets[block])
            result.append({
                "block": block, "needed": needed,
                "have": int(self._have[block]), "rank": rank,
                "rank_shortfall": needed - rank,
                "solved": block in self._solved,
            })
        return result

    def _solve_block(self, block: int, items: list[tuple[int, int]]
                     ) -> tuple[int, np.ndarray | None]:
        kb = self.code.k_per_block[block]
        if len(items) < kb:                 # rank cannot reach kb — skip
            return self._exact_rank(block, items), None
        src_esis = {r: esi for r, esi in items if r < kb}
        if len(src_esis) == kb:             # systematic fast path — no GE
            self._rank_cache[block] = (len(items), kb)
            return kb, np.stack([self._symbol_bits(src_esis[r])
                                 for r in range(kb)])
        rows = self._packed_generator_rows(items)
        vals = _pack_bits_2d(np.stack(
            [self._symbol_bits(esi) for _, esi in items]))
        rank, solved_p = _ge_solve_gf2(rows, vals, kb)
        self._rank_cache[block] = (len(items), int(rank))
        if solved_p is None:
            return rank, None
        return rank, _unpack_bits_2d(solved_p, self.code.s_bits)

    def audit_solved_symbols(self) -> tuple[int, ...]:
        """D16 report-only surplus audit: ESIs (ascending) of received
        symbols in SOLVED blocks whose certified value differs from
        re-encoding the block's solved source rows.

        Pivot rows are consistent by construction (the solved solution
        satisfies them exactly), so every hit is a DEPENDENT (surplus)
        equation whose disagreement Gauss-Jordan silently masked —
        including systematic-fast-path repair symbols the solve never
        consulted.  Pure observation: O(symbols x row weight), one bulk
        coefficient draw per block, no elimination, and no change to
        symbols, solve caches, or rank accounting.
        """
        if not self._solved:
            return ()
        mismatched: list[int] = []
        buckets = self._block_items()
        for block in sorted(self._solved):
            items = buckets[block]
            if not items:
                continue
            kb = self.code.k_per_block[block]
            solved_packed = np.packbits(self._solved[block], axis=1)
            repair = [(r, esi) for r, esi in items if r >= kb]
            expected_of: dict[int, np.ndarray] = {}
            if repair:
                rows = (
                    fountain_rows_bits(
                        self.code.seed, block,
                        [r for r, _esi in repair], kb)
                    if self.code.stream_id is None
                    else color_fountain_rows_bits(
                        self.code.seed, self.code.stream_id, block,
                        [r for r, _esi in repair], kb))
                for n, (_r, esi) in enumerate(repair):
                    sel = np.flatnonzero(rows[n])
                    expected_of[esi] = (
                        np.zeros(solved_packed.shape[1], np.uint8)
                        if sel.size == 0
                        else np.bitwise_xor.reduce(
                            solved_packed[sel], axis=0))
            for r, esi in items:
                expected = (
                    solved_packed[r] if r < kb else expected_of[esi])
                if not np.array_equal(self._symbols[esi], expected):
                    mismatched.append(esi)
        return tuple(sorted(mismatched))

    def try_solve(self) -> np.ndarray | None:
        """(k_total, s_bits) uint8 source bits when every block solves,
        else None (call rank_status for the per-block shortfall)."""
        buckets = self._block_items()
        for b in range(self.code.n_blocks):
            if b in self._solved:
                continue
            have = len(buckets[b])
            if self._failed_at.get(b) == have:
                continue                    # nothing new since last attempt
            if have < self.code.k_per_block[b]:
                # Decoding cannot succeed; defer GE until solve is possible
                # or a caller explicitly requests close-time rank diagnostics.
                self._failed_at[b] = have
                continue
            rank, solved = self._solve_block(b, buckets[b])
            if solved is None:
                self._failed_at[b] = have
            else:
                self._solved[b] = solved
                self._failed_at.pop(b, None)
        if len(self._solved) < self.code.n_blocks:
            return None
        out = np.zeros((self.code.k_total, self.code.s_bits), np.uint8)
        for b, solved in self._solved.items():
            off = self.code.block_offsets[b]
            out[off:off + self.code.k_per_block[b]] = solved
        return out

"""Layer 4 — outer fountain code across a multi-page volume (DESIGN.md §7, M3).

Makes ANY sufficient subset of certified tiles from ANY pages reconstruct the
whole volume — the R2 holographic property. Consumes CERTIFIED tiles only
(paperholo.ldpc's CRC-32 F9 layer owns cleanliness): the fountain assumes
error-free symbols; garbage-in is out-of-contract by architecture
(tiles_to_symbols drops every non-ok TileResult, that is the only gate here).

fountain-v1 = a DECLARED stand-in for DESIGN §7's RaptorQ with the same
function class: a SYSTEMATIC DENSE RANDOM-LINEAR FOUNTAIN over GF(2).
Grounds (decision record): RFC 6330 in pure numpy is large and table-heavy;
dense-RLF overhead is provable (~1.6 expected extra symbols per block,
P(fail) <= 2^-delta at K+delta received) and bit-packed Gaussian elimination
at K <= 4096 runs in seconds. Swapping in real RaptorQ later is a registry
entry change (payload-interpretation format axis — no layout_version bump:
the printed page is untouched, only the meaning of the user bits changes).

FORMAT-AXIS DERIVATION (fountain-v1, frozen — precise enough for a stranger
to reimplement from this docstring; tests/test_fountain.py pins sha256/
constant anchors):

  Symbol framing. A SYMBOL is one INTERIOR tile's fountain slice. Interior
  tile = an ldpc.tile_grid tile whose full 64x64 cells are on-page
  ((ty+1)*64 <= H and (tx+1)*64 <= W); enumerated in tile-grid raster order
  they get local indices 0..n_int-1. S = symbol_bits = the MINIMUM
  ldpc.tile_user_capacity over one page's interior tiles at the volume's
  LDPC rate (identical on every page: the pilot pattern is page-independent;
  deterministic from (ComposeSpec, seed, rate) alone). Each interior tile
  carries exactly one symbol in the FIRST S user bits of its per-tile
  payload (ldpc.encode_page's per_tile accounting: user bits
  [user_offset, user_offset + S) of the page user vector); the remaining
  cap - S bits are zero pads inside the tile CRC, stripped on decode.
  EDGE (non-interior) tiles carry NO symbol: their user bits are all zero —
  they still print and certify but are fountain-inert (measured cost on the
  e012 geometry at r0700: edge-tile capacity 2.33% + interior pad 0.26% of
  page user capacity).

  Geometric ESI (no headers — the pilot lattice already gives absolute
  (page, tile) addresses; headers cannot bootstrap, geometry can). Global
  tile index t enumerates interior tiles in (page, tile-raster) order:
  t = page * n_int + local. Block id b = t mod n_blocks; in-block index
  i = t // n_blocks — round-robin interleave, so any spatial region of the
  volume hits all blocks ~uniformly (the R2 requirement).

  Blocks. K_total = ceil(data_len_bytes*8 / S) source symbols;
  n_blocks = ceil(K_total / 4096); K_b = balanced split with the FIRST
  (K_total mod n_blocks) blocks taking the extra symbol. With that exact
  assignment, symbol (b, i) is SOURCE iff i < K_b iff its global index
  t = i*n_blocks + b < K_total: the first K_total tiles of the volume are
  exactly the source symbols (source-first layout — data lands on early
  pages, repair grows later; enlarging n_pages adds repair without
  re-encoding any source symbol: rateless growth).

  Generator rows. Source row (i < K_b) = the unit vector e_i (systematic).
  Repair row (i >= K_b) = modulation.rng(seed,
  b"fountain-v1/row/" + block.to_bytes(4,"little") + i.to_bytes(4,"little")
  ).integers(0, 2, K_b) — dense ~K_b/2 weight, defined for every i >= K_b
  (rateless). seed = VolumeSpec.seed, the same volume seed that keys
  compose/pilots/ldpc.

  Data mapping. data bytes -> bits via np.unpackbits (MSB-first within each
  byte), zero-padded to K_total*S; source symbol with GLOBAL index t carries
  bits [t*S, (t+1)*S). Block b's in-block source j is therefore global
  t = j*n_blocks + b. data_len_bytes is part of the volume descriptor and
  strips the pad on decode.

  VolumeSpec is the public volume descriptor (R5 note: in the archive it
  rides the bootstrap sheet / format registry; in-band replication is
  declared future work). Everything derivable is derived, never stored.

LEVEL-STRATIFIED VOLUMES (cmy8 pages, COLOR-DESIGN D2 — additive, the
single-level derivation above is untouched and byte-identical): n_levels=3
with per-level ldpc_rate_ids runs THREE parallel copies of the mapping
above, symbol = (page, tile, level). Per level l: S_l = that level's min
interior tile capacity at its rung (the shorten mask is level-independent);
data bytes partition across levels by cumulative-floor proportional split
on per-level source capacity (VolumeSpec.data_byte_boundaries); repair rows
key rng(seed, b"fountain-v1/row/" + <level:1> + <block:le32> + <i:le32>) —
the level byte enters ONLY for n_levels > 1 (single-level labels stay
frozen). Symbol dicts key (level, block, i); the volume decodes iff every
level solves.

Decoder core: per-block bit-packed Gauss-Jordan elimination over GF(2) —
generator rows packed 64 columns/uint64 word (little bit order: column c =
word c>>6, bit c&63), symbol values packed alongside and XORed with the
rows; deterministic (symbols processed in sorted (block, i) key order);
systematic fast path when all K_b source symbols of a block are present
(no GE). volume_decode returns per-block diagnostics
{received, needed, rank, solved, systematic} and honest partial results:
None + diag["partial_data"] (zeros where unsolved) when any block is
under-ranked.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from . import compose, ldpc
from .modulation import rng
from .pilots import PilotLayout

FOUNTAIN_VERSION = "fountain-v1"
BLOCK_K_MAX = 4096                     # max source symbols per fountain block
ROW_LABEL = b"fountain-v1/row/"        # + <block:le32> + <i:le32>
_WORD = np.dtype("<u8")                # frozen packing word (little-endian)


def _default_compose_spec() -> compose.ComposeSpec:
    """The e012 archive page (layout_version 3, kcell-c3, 2220x1500 cells)."""
    return compose.ComposeSpec(layout_version=3, pilot=PilotLayout(version=3))


@dataclass(frozen=True)
class VolumeSpec:
    """Public volume descriptor (format-axis). Everything derivable is a
    property; only (n_pages, data_len_bytes, seed, rate, page format) is
    stored. seed is the ONE volume seed: compose/pilots/ldpc AND the
    fountain generator rows all key off it.

    LEVEL-STRATIFIED volumes (cmy8, COLOR-DESIGN D2): n_levels = 3 with
    per-level ldpc_rate_ids — three PARALLEL symbol streams, symbol =
    (page, tile, level); each level solves independently with its own
    S_level (that level's min interior tile capacity at its rate rung);
    data bytes are partitioned across levels proportional to per-level
    capacity (cumulative-floor boundaries, exact). The scalar accessors
    (symbol_bits/k_total/n_blocks/k_per_block) are single-level only —
    color callers use the *_level accessors. n_levels = 1 volumes are
    byte-identical to the pre-color fountain (e016 golden)."""

    n_pages: int
    data_len_bytes: int
    seed: bytes
    ldpc_rate_id: str = "r0700"
    compose_spec: compose.ComposeSpec = field(
        default_factory=_default_compose_spec)
    n_levels: int = 1
    ldpc_rate_ids: tuple[str, ...] | None = None    # per-level rungs (C,M,Y)

    def __post_init__(self) -> None:
        if self.n_pages < 1:
            raise ValueError("n_pages must be >= 1")
        if self.data_len_bytes < 1:
            raise ValueError("data_len_bytes must be >= 1")
        if not isinstance(self.seed, bytes) or not self.seed:
            raise ValueError("seed must be non-empty bytes")
        if self.ldpc_rate_id not in ldpc.LDPC_LADDER:
            raise ValueError(f"unknown ldpc_rate_id {self.ldpc_rate_id!r} "
                             f"(ladder: {sorted(ldpc.LDPC_LADDER)})")
        if self.n_levels not in (1, 3):
            raise ValueError(f"n_levels must be 1 or 3, got {self.n_levels}")
        if self.n_levels != self.compose_spec.n_levels:
            raise ValueError(
                f"n_levels {self.n_levels} != compose_spec.n_levels "
                f"{self.compose_spec.n_levels}")
        if self.n_levels == 3:
            if self.ldpc_rate_ids is None or len(self.ldpc_rate_ids) != 3:
                raise ValueError("level-stratified volumes need "
                                 "ldpc_rate_ids = 3 per-level rungs (C,M,Y)")
            for rid in self.ldpc_rate_ids:
                if rid not in ldpc.LDPC_LADDER:
                    raise ValueError(f"unknown ldpc_rate_id {rid!r} "
                                     f"(ladder: {sorted(ldpc.LDPC_LADDER)})")
            if not isinstance(self.ldpc_rate_ids, tuple):
                object.__setattr__(self, "ldpc_rate_ids",
                                   tuple(self.ldpc_rate_ids))
        elif self.ldpc_rate_ids is not None:
            raise ValueError("ldpc_rate_ids is a level-stratified (n_levels="
                             "3) field; single-level uses ldpc_rate_id")
        if self.compose_spec.layout_version in (3, 4):
            ty, tx = self.compose_spec.page_tiles_yx
            max_pages = (2 ** 18 - 1) // (ty * tx)
            if self.n_pages > max_pages:
                raise ValueError(
                    f"n_pages {self.n_pages} exceeds the v3 pilot flat-counter "
                    f"cap {max_pages} for this page geometry")

    def _single_level_only(self, what: str) -> None:
        if self.n_levels != 1:
            raise ValueError(f"{what} is single-level API; this volume is "
                             f"level-stratified — use the *_level accessor")

    @property
    def rate_ids(self) -> tuple[str, ...]:
        """Per-level rate rungs; (ldpc_rate_id,) for single-level volumes."""
        if self.n_levels == 1:
            return (self.ldpc_rate_id,)
        assert self.ldpc_rate_ids is not None
        return self.ldpc_rate_ids

    @property
    def ldpc_spec(self) -> ldpc.LdpcSpec:
        self._single_level_only("ldpc_spec")
        return ldpc.LDPC_LADDER[self.ldpc_rate_id]

    def ldpc_spec_level(self, level: int) -> ldpc.LdpcSpec:
        return ldpc.LDPC_LADDER[self.rate_ids[level]]

    @property
    def data_bits(self) -> int:
        return self.data_len_bytes * 8

    @property
    def symbol_bits(self) -> int:
        """S: min interior-tile user capacity (see module docstring)."""
        self._single_level_only("symbol_bits")
        return _symbol_geometry(self)["symbol_bits"]

    def symbol_bits_level(self, level: int) -> int:
        """S_level: that level's min interior tile capacity at its rung."""
        return _symbol_geometry_level(self, level)["symbol_bits"]

    @property
    def n_interior_tiles_per_page(self) -> int:
        # interior tiles depend on page geometry only — level-independent
        return len(_symbol_geometry_level(self, 0)["interior_tile_yx"])

    @property
    def n_symbols_total(self) -> int:
        """Symbol-bearing tiles per level (per-level stream length)."""
        return self.n_pages * self.n_interior_tiles_per_page

    @property
    def source_capacity_bits(self) -> int:
        self._single_level_only("source_capacity_bits")
        return self.n_symbols_total * self.symbol_bits

    def source_capacity_bits_level(self, level: int) -> int:
        return self.n_symbols_total * self.symbol_bits_level(level)

    def data_byte_boundaries(self) -> tuple[int, ...]:
        """Per-level data partition (cumulative-floor proportional split on
        per-level source capacity): level l carries data bytes
        [b[l], b[l+1]). For n_levels == 1: (0, data_len_bytes)."""
        caps = [self.source_capacity_bits_level(lv)
                for lv in range(self.n_levels)]
        total = sum(caps)
        cum = 0
        bounds = [0]
        for c in caps:
            cum += c
            bounds.append((self.data_len_bytes * cum) // total)
        assert bounds[-1] == self.data_len_bytes
        return tuple(bounds)

    def data_len_bytes_level(self, level: int) -> int:
        b = self.data_byte_boundaries()
        return b[level + 1] - b[level]

    @property
    def k_total(self) -> int:
        self._single_level_only("k_total")
        return -(-self.data_bits // self.symbol_bits)

    def k_total_level(self, level: int) -> int:
        """Source symbols of level `level` (0 when the level carries no
        bytes — possible only for tiny volumes; the level is then trivially
        solved)."""
        if self.n_levels == 1:
            return self.k_total
        n_bytes = self.data_len_bytes_level(level)
        return -(-(n_bytes * 8) // self.symbol_bits_level(level))

    @property
    def n_blocks(self) -> int:
        self._single_level_only("n_blocks")
        return -(-self.k_total // BLOCK_K_MAX)

    def n_blocks_level(self, level: int) -> int:
        if self.n_levels == 1:
            return self.n_blocks
        return -(-self.k_total_level(level) // BLOCK_K_MAX)

    @property
    def k_per_block(self) -> tuple[int, ...]:
        """Balanced split; the FIRST (k_total mod n_blocks) blocks take the
        extra symbol (load-bearing: makes source == the first K_total global
        tile indices exactly — see the ESI derivation)."""
        self._single_level_only("k_per_block")
        nb = self.n_blocks
        base, rem = divmod(self.k_total, nb)
        return tuple(base + 1 if b < rem else base for b in range(nb))

    def k_per_block_level(self, level: int) -> tuple[int, ...]:
        if self.n_levels == 1:
            return self.k_per_block
        kt, nb = self.k_total_level(level), self.n_blocks_level(level)
        if nb == 0:
            return ()
        base, rem = divmod(kt, nb)
        return tuple(base + 1 if b < rem else base for b in range(nb))


# ---------------------------------------------------------------------------
# geometry / ESI
# ---------------------------------------------------------------------------

_GEOM_CACHE: dict = {}


def interior_tiles(compose_spec: compose.ComposeSpec) -> list[tuple[int, int]]:
    """Interior (full 64x64 on-page) tiles in tile-grid raster order — the
    symbol-bearing tiles; local index = list position."""
    h, w = compose_spec.page_cells_yx
    tc = ldpc.TILE_CELLS
    return [(ty, tx) for (ty, tx) in ldpc.tile_grid(compose_spec.page_cells_yx)
            if (ty + 1) * tc <= h and (tx + 1) * tc <= w]


def _symbol_geometry(vspec: VolumeSpec) -> dict:
    """Cached page-level symbol geometry: S, interior tiles, per-tile caps
    (deterministic from (compose_spec, seed, rate) alone — n_pages/data_len
    do not enter). Single-level volumes only (frozen path); color levels go
    through _symbol_geometry_level."""
    return _symbol_geometry_rate(vspec.compose_spec, vspec.seed,
                                 vspec.ldpc_rate_id)


def _symbol_geometry_level(vspec: VolumeSpec, level: int) -> dict:
    """Per-level geometry at that level's rate rung (level-independent for
    n_levels == 1, where rate_ids == (ldpc_rate_id,))."""
    return _symbol_geometry_rate(vspec.compose_spec, vspec.seed,
                                 vspec.rate_ids[level])


def _symbol_geometry_rate(cspec: compose.ComposeSpec, seed: bytes,
                          rate_id: str) -> dict:
    key = (cspec, seed, rate_id)
    if key in _GEOM_CACHE:
        return _GEOM_CACHE[key]
    lspec = ldpc.LDPC_LADDER[rate_id]
    interior = interior_tiles(cspec)
    if not interior:
        raise ValueError(f"page {cspec.page_cells_yx} has no interior "
                         "(full 64x64) tiles — no symbol can be carried")
    tile_cap = {t: ldpc.tile_user_capacity(
                    ldpc.tile_shorten_mask(t, cspec, seed), lspec)
                for t in ldpc.tile_grid(cspec.page_cells_yx)}
    s_bits = min(tile_cap[t] for t in interior)
    if s_bits < 1:
        raise ValueError("interior tile capacity is 0 at this rate")
    page_cap = sum(tile_cap.values())
    int_cap = sum(tile_cap[t] for t in interior)
    geo = {
        "symbol_bits": s_bits,
        "interior_tile_yx": tuple(interior),
        "interior_local_index": {t: j for j, t in enumerate(interior)},
        "tile_cap": tile_cap,
        "page_user_capacity_bits": page_cap,
        "fountain_inert_capacity_fraction": (page_cap - int_cap) / page_cap,
        "pad_capacity_fraction": (int_cap - len(interior) * s_bits) / page_cap,
    }
    _GEOM_CACHE[key] = geo
    return geo


def volume_geometry(vspec: VolumeSpec) -> dict:
    """Full volume geometry + capacity check (raises if the data does not
    fit: k_total > n_symbols_total). The tile t <-> (page, tile_yx) maps are
    the interior list (local index -> tile_yx; t = page*n_int + local) plus
    esi_of_tile / tile_of_symbol.

    Level-stratified volumes: per-level checks + a "levels" list of
    per-level geometries (each the single-level dict shape)."""
    if vspec.n_levels != 1:
        levels = []
        bounds = vspec.data_byte_boundaries()
        for lv in range(vspec.n_levels):
            g = dict(_symbol_geometry_level(vspec, lv))
            g.update(level=lv, ldpc_rate_id=vspec.rate_ids[lv],
                     data_len_bytes=vspec.data_len_bytes_level(lv),
                     k_total=vspec.k_total_level(lv),
                     n_blocks=vspec.n_blocks_level(lv),
                     k_per_block=vspec.k_per_block_level(lv),
                     source_capacity_bits=vspec.source_capacity_bits_level(lv))
            if g["k_total"] > vspec.n_symbols_total:
                raise ValueError(
                    f"data does not fit level {lv}: k_total {g['k_total']} > "
                    f"{vspec.n_symbols_total} symbol-bearing tiles "
                    f"(S_{lv} = {g['symbol_bits']})")
            levels.append(g)
        return {"n_pages": vspec.n_pages,
                "n_interior_tiles_per_page": vspec.n_interior_tiles_per_page,
                "n_symbols_total": vspec.n_symbols_total,
                "n_levels": vspec.n_levels,
                "data_byte_boundaries": bounds,
                "levels": levels}
    geo = dict(_symbol_geometry(vspec))
    n_int = len(geo["interior_tile_yx"])
    geo.update(
        n_pages=vspec.n_pages,
        n_interior_tiles_per_page=n_int,
        n_symbols_total=vspec.n_symbols_total,
        k_total=vspec.k_total,
        n_blocks=vspec.n_blocks,
        k_per_block=vspec.k_per_block,
        source_capacity_bits=vspec.source_capacity_bits,
    )
    if vspec.k_total > vspec.n_symbols_total:
        raise ValueError(
            f"data does not fit: k_total {vspec.k_total} source symbols > "
            f"{vspec.n_symbols_total} symbol-bearing tiles "
            f"({vspec.n_pages} pages x {n_int}; S = {geo['symbol_bits']})")
    return geo


def esi_of_tile(vspec: VolumeSpec, page: int, tile_yx: tuple[int, int],
                level: int = 0):
    """ESI of a tile's symbol, or None for fountain-inert (non-interior)
    tiles. Raises on a page outside the volume. Single-level volumes return
    (block, in_block_index) — unchanged; level-stratified volumes return
    (level, block, in_block_index) for the given level (symbol =
    (page, tile, level), D2)."""
    if not 0 <= page < vspec.n_pages:
        raise ValueError(f"page {page} outside volume [0, {vspec.n_pages})")
    if not 0 <= level < vspec.n_levels:
        raise ValueError(f"level {level} outside [0, {vspec.n_levels})")
    geo = _symbol_geometry_level(vspec, level)
    local = geo["interior_local_index"].get(tuple(tile_yx))
    if local is None:
        return None
    t = page * len(geo["interior_tile_yx"]) + local
    nb = (vspec.n_blocks if vspec.n_levels == 1
          else vspec.n_blocks_level(level))
    if nb == 0:            # zero-byte level (tiny volume): no symbols
        return None
    if vspec.n_levels == 1:
        return t % nb, t // nb
    return level, t % nb, t // nb


def tile_of_symbol(vspec: VolumeSpec, block: int, i: int, level: int = 0
                   ) -> tuple[int, tuple[int, int]]:
    """Inverse map: symbol (block, i) [of `level`] -> (page, tile_yx).
    Raises if the symbol lies beyond the volume's pages."""
    nb = (vspec.n_blocks if vspec.n_levels == 1
          else vspec.n_blocks_level(level))
    if not 0 <= block < nb:
        raise ValueError(f"block {block} outside [0, {nb})")
    if i < 0:
        raise ValueError("in-block index must be >= 0")
    t = i * nb + block
    if t >= vspec.n_symbols_total:
        raise ValueError(f"symbol ({block}, {i}) = global tile {t} beyond "
                         f"the volume's {vspec.n_symbols_total} tiles")
    geo = _symbol_geometry_level(vspec, level)
    n_int = len(geo["interior_tile_yx"])
    page, local = divmod(t, n_int)
    return page, geo["interior_tile_yx"][local]


def generator_row(vspec: VolumeSpec, block: int, i: int,
                  level: int = 0) -> np.ndarray:
    """(K_b,) uint8 generator row of symbol (block, i): unit e_i for
    i < K_b (systematic), seeded dense row otherwise (frozen derivation in
    the module docstring; defined for every i >= K_b — rateless).

    Level-stratified volumes prefix the row label with the level byte
    (b"fountain-v1/row/" + <level:1> + <block:le32> + <i:le32>) so no two
    levels share a repair row; single-level volumes keep the frozen label
    byte-identical."""
    nb = (vspec.n_blocks if vspec.n_levels == 1
          else vspec.n_blocks_level(level))
    if not 0 <= block < nb:
        raise ValueError(f"block {block} outside [0, {nb})")
    if i < 0:
        raise ValueError("in-block index must be >= 0")
    kb = (vspec.k_per_block[block] if vspec.n_levels == 1
          else vspec.k_per_block_level(level)[block])
    if i < kb:
        row = np.zeros(kb, np.uint8)
        row[i] = 1
        return row
    lvl_prefix = b"" if vspec.n_levels == 1 else bytes([level])
    g = rng(vspec.seed, ROW_LABEL + lvl_prefix
            + block.to_bytes(4, "little") + i.to_bytes(4, "little"))
    # no dtype kwarg (house-rule exception): this is the FROZEN v1 row
    # derivation — the K label stream is golden-pinned (e016) and a dtype
    # kwarg would fork the Philox stream. v4 level rows deliberately reuse
    # the single shared derivation (encoder and decoder both call HERE; no
    # retyped twin exists for the 012.3 failure mode to bite).
    return g.integers(0, 2, kb).astype(np.uint8)


# ---------------------------------------------------------------------------
# bit packing + GF(2) Gauss-Jordan core
# ---------------------------------------------------------------------------


def _pack_bits_2d(bits: np.ndarray) -> np.ndarray:
    """(R, L) {0,1} uint8 -> (R, ceil(L/64)) uint64: column c = bit (c & 63)
    of word (c >> 6), little bit order (frozen packing of the GE core)."""
    b = np.ascontiguousarray(np.asarray(bits, np.uint8))
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
    generator rows; vals (R, Wv) uint64 packed symbol values, XORed alongside.
    Column-order partial pivot (first available row) — deterministic.
    Returns (rank, solved): solved is (k, Wv) packed source values (row j =
    in-block source j) when rank == k, else None."""
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


# ---------------------------------------------------------------------------
# encode
# ---------------------------------------------------------------------------


def _level_params(vspec: VolumeSpec, level: int
                  ) -> tuple[int, int, tuple[int, ...]]:
    """(S, n_blocks, k_per_block) of one level (level 0 == the scalar path
    for single-level volumes)."""
    if vspec.n_levels == 1:
        return vspec.symbol_bits, vspec.n_blocks, vspec.k_per_block
    return (vspec.symbol_bits_level(level), vspec.n_blocks_level(level),
            vspec.k_per_block_level(level))


def _block_source_packed(vspec: VolumeSpec, source_bits: np.ndarray,
                         cache: dict, block: int, level: int = 0
                         ) -> np.ndarray:
    """Packed (K_b, W) source matrix of one block (in-block source j = global
    tile t = j*n_blocks + block), lazily cached (key = (level, block))."""
    if (level, block) not in cache:
        _, nb, kpb = _level_params(vspec, level)
        kb = kpb[block]
        idx = np.arange(kb, dtype=np.int64) * nb + block
        cache[(level, block)] = _pack_bits_2d(source_bits[idx])
    return cache[(level, block)]


def _symbol_value(vspec: VolumeSpec, source_bits: np.ndarray, cache: dict,
                  block: int, i: int, level: int = 0) -> np.ndarray:
    """(S,) uint8 value of symbol (block, i) [of `level`] from that level's
    padded source bits."""
    s_bits, nb, kpb = _level_params(vspec, level)
    kb = kpb[block]
    if i < kb:
        return source_bits[i * nb + block].copy()
    sel = np.flatnonzero(generator_row(vspec, block, i, level=level))
    if sel.size == 0:
        return np.zeros(s_bits, np.uint8)
    packed = _block_source_packed(vspec, source_bits, cache, block, level)
    acc = np.bitwise_xor.reduce(packed[sel], axis=0)
    return np.unpackbits(acc.view(np.uint8), bitorder="little",
                         count=s_bits).astype(np.uint8)


@dataclass(eq=False)
class VolumeEncoding:
    """volume_encode output: the padded source symbols + per-page user-bit
    vectors sized ldpc.page_user_capacity, ready for ldpc.encode_page ->
    compose.compose_page (page index = list position).

    Level-stratified volumes hold LISTS: source_bits = [3 x (k_total_l,
    S_l)], page_user_bits[page] = [3 per-level user vectors]."""

    vspec: VolumeSpec
    source_bits: np.ndarray            # (k_total, S) uint8 padded data slices
    page_user_bits: list               # n_pages vectors of {0,1} uint8
    _packed_cache: dict = field(default_factory=dict, repr=False)

    def symbol(self, block: int, i: int, level: int = 0) -> np.ndarray:
        """(S,) uint8 value of any symbol of the volume (source or repair)."""
        src = (self.source_bits if self.vspec.n_levels == 1
               else self.source_bits[level])
        return _symbol_value(self.vspec, src, self._packed_cache,
                             block, i, level=level)


def volume_encode(data: bytes, vspec: VolumeSpec,
                  seed: bytes | None = None) -> VolumeEncoding:
    """data -> VolumeEncoding (see module docstring for the frozen mapping).

    seed, if given, must equal vspec.seed (the volume seed lives in the
    descriptor — decode-side determinism needs it there; the parameter is
    kept for call-site explicitness only). Raises if the data does not fit
    the volume or len(data) != vspec.data_len_bytes."""
    if seed is not None and seed != vspec.seed:
        raise ValueError("seed disagrees with vspec.seed (the volume seed is "
                         "part of the descriptor)")
    geo = volume_geometry(vspec)          # includes the capacity check
    if len(data) != vspec.data_len_bytes:
        raise ValueError(f"data is {len(data)} bytes, VolumeSpec says "
                         f"{vspec.data_len_bytes}")
    if vspec.n_levels != 1:
        return _volume_encode_mlc(data, vspec, geo)
    s_bits = geo["symbol_bits"]
    k_total = vspec.k_total
    bits = np.unpackbits(np.frombuffer(data, np.uint8))
    padded = np.zeros(k_total * s_bits, np.uint8)
    padded[:bits.size] = bits
    source_bits = padded.reshape(k_total, s_bits)

    cache: dict = {}
    tiles_all = ldpc.tile_grid(vspec.compose_spec.page_cells_yx)
    tile_cap = geo["tile_cap"]
    local_index = geo["interior_local_index"]
    n_int = geo["n_interior_tiles_per_page"]
    nb = vspec.n_blocks
    pages: list[np.ndarray] = []
    for page in range(vspec.n_pages):
        parts: list[np.ndarray] = []
        for tile in tiles_all:
            vec = np.zeros(tile_cap[tile], np.uint8)
            local = local_index.get(tile)
            if local is not None:
                t = page * n_int + local
                vec[:s_bits] = _symbol_value(vspec, source_bits, cache,
                                             t % nb, t // nb)
            parts.append(vec)
        pages.append(np.concatenate(parts))
    return VolumeEncoding(vspec=vspec, source_bits=source_bits,
                          page_user_bits=pages)


def _volume_encode_mlc(data: bytes, vspec: VolumeSpec,
                       geo: dict) -> VolumeEncoding:
    """Level-stratified encode: the single-level mapping applied per level
    to that level's data slice (data_byte_boundaries partition)."""
    bounds = geo["data_byte_boundaries"]
    cache: dict = {}
    source_per_level: list[np.ndarray] = []
    for lv in range(vspec.n_levels):
        lgeo = geo["levels"][lv]
        s_bits, k_total = lgeo["symbol_bits"], lgeo["k_total"]
        bits = np.unpackbits(np.frombuffer(
            data[bounds[lv]:bounds[lv + 1]], np.uint8))
        padded = np.zeros(max(k_total, 0) * s_bits, np.uint8)
        padded[:bits.size] = bits
        source_per_level.append(padded.reshape(max(k_total, 0), s_bits))

    tiles_all = ldpc.tile_grid(vspec.compose_spec.page_cells_yx)
    n_int = vspec.n_interior_tiles_per_page
    pages: list[list[np.ndarray]] = []
    for page in range(vspec.n_pages):
        per_level: list[np.ndarray] = []
        for lv in range(vspec.n_levels):
            lgeo = geo["levels"][lv]
            s_bits, nb = lgeo["symbol_bits"], lgeo["n_blocks"]
            tile_cap = lgeo["tile_cap"]
            local_index = lgeo["interior_local_index"]
            parts: list[np.ndarray] = []
            for tile in tiles_all:
                vec = np.zeros(tile_cap[tile], np.uint8)
                local = local_index.get(tile)
                if local is not None and nb > 0:
                    t = page * n_int + local
                    vec[:s_bits] = _symbol_value(
                        vspec, source_per_level[lv], cache,
                        t % nb, t // nb, level=lv)
                parts.append(vec)
            per_level.append(np.concatenate(parts))
        pages.append(per_level)
    return VolumeEncoding(vspec=vspec, source_bits=source_per_level,
                          page_user_bits=pages, _packed_cache=cache)


def encode_volume_pages(data: bytes, vspec: VolumeSpec) -> list[dict]:
    """Convenience wrapper: volume_encode -> ldpc.encode_page per page.
    Returns one ldpc.encode_page dict per page (payload_bits ready for
    compose.compose_page(..., page=p)) with "page" added. Level-stratified
    volumes get ldpc's level-aware dicts (lists in every slot)."""
    enc = volume_encode(data, vspec)
    out = []
    for page, user in enumerate(enc.page_user_bits):
        if vspec.n_levels == 1:
            d = ldpc.encode_page(user, vspec.compose_spec, vspec.seed,
                                 vspec.ldpc_spec)
        else:
            d = ldpc.encode_page(
                user, vspec.compose_spec, vspec.seed,
                [vspec.ldpc_spec_level(lv) for lv in range(vspec.n_levels)])
        d["page"] = page
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# decode
# ---------------------------------------------------------------------------


def tiles_to_symbols(tile_results: Iterable, vspec: VolumeSpec
                     ) -> dict[tuple, np.ndarray]:
    """(page, TileResult) pairs -> certified symbol dict keyed
    (block, in_block_index). Drops: non-ok results (F9 gate — the fountain
    consumes CERTIFIED tiles only), fountain-inert (non-interior) tiles,
    pages outside the volume, duplicate symbols (first certified wins —
    rescan dedup). Strips the per-tile zero pad (keeps the first S bits).
    Raises if a certified interior tile's payload is shorter than S (that is
    a volume-descriptor mismatch, not a channel event).

    Level-stratified volumes take (page, level, TileResult) triples —
    levels certify independently, D2 — and key the dict (level, block, i)."""
    out: dict[tuple, np.ndarray] = {}
    for item in tile_results:
        if vspec.n_levels == 1:
            page, tr = item
            level = 0
        else:
            if len(item) != 3:
                raise ValueError("level-stratified volumes take (page, "
                                 "level, TileResult) triples")
            page, level, tr = item
            # validate BEFORE symbol_bits_level: an out-of-range positive
            # level would otherwise escape as an uncontracted IndexError
            # from VolumeSpec.rate_ids[level]
            if not 0 <= level < vspec.n_levels:
                raise ValueError(
                    f"level {level} outside [0, {vspec.n_levels})")
        if not tr.ok or tr.payload_bits is None:
            continue
        if not 0 <= page < vspec.n_pages:
            continue
        s_bits = (vspec.symbol_bits if vspec.n_levels == 1
                  else vspec.symbol_bits_level(level))
        key = esi_of_tile(vspec, page, tuple(tr.tile_yx), level=level)
        if key is None or key in out:
            continue
        pb = np.asarray(tr.payload_bits, np.uint8).ravel()
        if pb.size < s_bits:
            raise ValueError(
                f"certified interior tile {tuple(tr.tile_yx)} page {page} "
                f"level {level} carries {pb.size} user bits < S = {s_bits}: "
                "the TileResults were decoded against a different "
                "volume/rate than vspec")
        out[key] = pb[:s_bits].copy()
    return out


def _solve_blocks(buckets: dict, vspec: VolumeSpec, nb: int, k_total: int,
                  kpb: tuple[int, ...], s_bits: int, level: int
                  ) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Per-block solve core (the frozen single-level semantics, shared by
    both paths): systematic fast path, else packed GF(2) Gauss-Jordan.
    Returns (source (k_total, S), recovered (k_total,) bool, blocks_diag)."""
    source = np.zeros((k_total, s_bits), np.uint8)
    recovered = np.zeros(k_total, bool)
    blocks_diag: list[dict] = []
    for b in range(nb):
        got = sorted(buckets[b], key=lambda iv: iv[0])
        kb = kpb[b]
        n_recv = len(got)
        src_i = {i for i, _ in got if i < kb}
        systematic = len(src_i) == kb
        if systematic:
            vals = {i: v for i, v in got if i < kb}
            solved = np.stack([vals[j] for j in range(kb)])
            rank = kb
        elif n_recv == 0:
            solved, rank = None, 0
        else:
            rows = _pack_bits_2d(np.stack(
                [generator_row(vspec, b, i, level=level) for i, _ in got]))
            vals_p = _pack_bits_2d(np.stack([v for _, v in got]))
            rank, solved_p = _ge_solve_gf2(rows, vals_p, kb)
            solved = (None if solved_p is None
                      else _unpack_bits_2d(solved_p, s_bits))
        ok = solved is not None
        blocks_diag.append({"block": b, "received": n_recv, "needed": kb,
                            "rank": int(rank), "solved": ok,
                            "systematic": bool(systematic)})
        if ok:
            t_idx = np.arange(kb, dtype=np.int64) * nb + b
            source[t_idx] = solved
            recovered[t_idx] = True
    return source, recovered, blocks_diag


def volume_decode(symbols: dict, vspec: VolumeSpec
                  ) -> tuple[bytes | None, dict]:
    """Certified symbols -> (data, diag). symbols keyed (block, i) -> (S,)
    {0,1} arrays (from tiles_to_symbols; error-free by architecture — F9
    upstream owns cleanliness, a corrupted value decodes to wrong data with
    no flag here).

    Per block: systematic fast path when all K_b source symbols are present,
    else bit-packed GF(2) Gauss-Jordan (deterministic: sorted key order).
    Returns (data_bytes, diag) when every block solves; (None, diag) when any
    block is under-ranked — diag then carries "partial_data" (zeros where
    unsolved) and "symbol_recovered" ((k_total,) bool). diag["blocks"][b] =
    {block, received, needed, rank, solved, systematic}.

    Level-stratified volumes: symbols keyed (level, block, i); each level
    solves independently (its own blocks/rows/S) and the volume decodes iff
    ALL levels solve (D2). diag then carries per-level dicts under "levels"
    (each shaped like the single-level diag) + the volume verdict."""
    if vspec.n_levels != 1:
        return _volume_decode_mlc(symbols, vspec)
    geo = volume_geometry(vspec)
    s_bits = geo["symbol_bits"]
    nb, k_total = vspec.n_blocks, vspec.k_total
    kpb = vspec.k_per_block

    buckets: dict[int, list[tuple[int, np.ndarray]]] = {b: [] for b in range(nb)}
    for (block, i), val in symbols.items():
        if not 0 <= block < nb:
            raise ValueError(f"symbol block {block} outside [0, {nb})")
        if i < 0:
            raise ValueError("symbol in-block index must be >= 0")
        v = np.asarray(val, np.uint8).ravel()
        if v.size != s_bits:
            raise ValueError(f"symbol ({block},{i}) has {v.size} bits, "
                             f"S = {s_bits}")
        buckets[block].append((i, v))

    source, recovered, blocks_diag = _solve_blocks(
        buckets, vspec, nb, k_total, kpb, s_bits, level=0)

    diag = {"n_blocks": nb, "k_total": k_total, "symbol_bits": s_bits,
            "n_symbols_received": len(symbols), "blocks": blocks_diag,
            "solved_blocks": [d["block"] for d in blocks_diag if d["solved"]],
            "solved_all": all(d["solved"] for d in blocks_diag)}
    payload = np.packbits(source.reshape(-1)[:vspec.data_bits]).tobytes()
    if diag["solved_all"]:
        return payload, diag
    diag["partial_data"] = payload
    diag["symbol_recovered"] = recovered
    return None, diag


def _volume_decode_mlc(symbols: dict, vspec: VolumeSpec
                       ) -> tuple[bytes | None, dict]:
    """Level-stratified decode: per-level solve + byte reassembly along
    data_byte_boundaries. All levels must solve (D2)."""
    bounds = vspec.data_byte_boundaries()
    level_diags: list[dict] = []
    level_payloads: list[bytes] = []
    for lv in range(vspec.n_levels):
        s_bits, nb, kpb = _level_params(vspec, lv)
        k_total = vspec.k_total_level(lv)
        buckets: dict[int, list[tuple[int, np.ndarray]]] = {
            b: [] for b in range(nb)}
        n_recv = 0
        for key, val in symbols.items():
            if len(key) != 3:
                raise ValueError("level-stratified volumes key symbols "
                                 "(level, block, i)")
            level, block, i = key
            if level != lv:
                continue
            if not 0 <= block < nb:
                raise ValueError(f"symbol block {block} outside [0, {nb}) "
                                 f"at level {lv}")
            if i < 0:
                raise ValueError("symbol in-block index must be >= 0")
            v = np.asarray(val, np.uint8).ravel()
            if v.size != s_bits:
                raise ValueError(f"symbol ({lv},{block},{i}) has {v.size} "
                                 f"bits, S_{lv} = {s_bits}")
            buckets[block].append((i, v))
            n_recv += 1
        source, recovered, blocks_diag = _solve_blocks(
            buckets, vspec, nb, k_total, kpb, s_bits, level=lv)
        n_bytes = bounds[lv + 1] - bounds[lv]
        payload = np.packbits(
            source.reshape(-1)[:n_bytes * 8]).tobytes() if k_total else b""
        level_payloads.append(payload)
        level_diags.append(
            {"level": lv, "n_blocks": nb, "k_total": k_total,
             "symbol_bits": s_bits, "n_symbols_received": n_recv,
             "blocks": blocks_diag,
             "solved_blocks": [d["block"] for d in blocks_diag
                               if d["solved"]],
             "solved_all": all(d["solved"] for d in blocks_diag),
             "symbol_recovered": recovered})
    diag = {"n_levels": vspec.n_levels,
            "data_byte_boundaries": bounds,
            "n_symbols_received": len(symbols),
            "levels": level_diags,
            "solved_all": all(d["solved_all"] for d in level_diags)}
    data = b"".join(level_payloads)
    assert len(data) == vspec.data_len_bytes
    if diag["solved_all"]:
        return data, diag
    diag["partial_data"] = data
    return None, diag

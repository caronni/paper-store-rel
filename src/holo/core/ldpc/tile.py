"""64x64-cell tile framing for the colocated v1 format (HOLO-DESIGN §4).

PROVENANCE: CRC framing ported from src/paperholo/ldpc.py (_crc32_bits,
the [user | CRC-32 | shortened-zero-tail] info layout). The slot layout
itself is NEW to v1 and simpler than paperholo's: colocation gives every
tile the SAME site count (exact-100 pilots + F fillers, F4/§4.2), so
shortening is uniform count-shortening of the INFO TAIL only — parity is
always transmitted, there are no degenerate tiles and no overflow into
parity. The tile-invariant shorten pattern is broken by the per-tile
affine slot permutation (F16/§4.4): transmitted-bit j lives at cell
nonsite_cells[(a_t*j + b_t) mod T], with (a_t, b_t) drawn by
holo.core.keystream.slot_perm_params at the format layer — this module
takes them as ints and enforces gcd(a_t, T) == 1 (bijectivity).

LLR convention (house-wide): POSITIVE = bit 1; 0.0 = erasure; +-inf =
known bit. Shortened info-tail positions enter the decoder as -inf
(known 0). decode_tile NEVER returns ok=True with an uncertified payload:
syndrome AND CRC-32 both gate (F9 certification discipline carried).
"""
from __future__ import annotations

import math
import zlib
from dataclasses import dataclass

import numpy as np

from .construct import LADDER
from .decode import decode, encode

TILE_CELLS = 64
N_CELLS = 4096
CRC_BITS = 32

# v1 invariant: the mother-code length IS the tile slot count, so the
# transmitted-position count and the non-site cell count coincide.
assert all(spec.n_bits == N_CELLS for spec in LADDER.values())


def crc32_bits(bits: np.ndarray) -> np.ndarray:
    """(32,) uint8, MSB-first big-endian zlib.crc32 over the bits packed
    MSB-first into bytes (np.packbits, last byte zero-padded) — ported
    exactly from paperholo ldpc._crc32_bits."""
    b = np.packbits(np.asarray(bits, np.uint8)).tobytes()
    c = zlib.crc32(b) & 0xFFFFFFFF
    return ((c >> (31 - np.arange(CRC_BITS))) & 1).astype(np.uint8)


def tile_capacity(rate_id: str, n_sites: int) -> int:
    """User bits per tile = k_bits - 32 - n_sites. Uniform by construction
    (every tile carries the same site count); raises if the rung cannot
    host the site count at all."""
    cap = LADDER[rate_id].k_bits - CRC_BITS - n_sites
    if n_sites < 0 or cap <= 0:
        raise ValueError(f"{rate_id}: n_sites={n_sites} leaves no capacity")
    return cap


def transmitted_positions(rate_id: str, n_sites: int) -> np.ndarray:
    """Codeword positions that go on paper, ascending: [0, k-n_sites) ++
    [k, n). Shortening consumes the INFO TAIL only (paperholo convention,
    load-bearing: parity is always transmitted). Length T = n - n_sites."""
    spec = LADDER[rate_id]
    tile_capacity(rate_id, n_sites)          # validates n_sites
    return np.concatenate([
        np.arange(spec.k_bits - n_sites, dtype=np.int64),
        np.arange(spec.k_bits, spec.n_bits, dtype=np.int64)])


def _validated_site_cells(site_cells: np.ndarray) -> np.ndarray:
    sc = np.asarray(site_cells, np.int64).ravel()
    if sc.size:
        if int(sc.min()) < 0 or int(sc.max()) >= N_CELLS:
            raise ValueError("site_cells out of [0, 4096)")
        if (np.diff(sc) <= 0).any():
            raise ValueError("site_cells must be strictly increasing")
    return sc


def cell_map(site_cells: np.ndarray, a_t: int, b_t: int) -> np.ndarray:
    """(T,) int64: transmitted-bit j lives at in-tile cell (slot-raster
    index) nonsite_cells[(a_t*j + b_t) mod T], nonsite_cells = the sorted
    complement of site_cells in [0, 4096). (a_t, b_t) come from
    keystream.slot_perm_params(seed, tile_counter, T); a_t must be coprime
    to T (bijectivity) and both must lie in [0, T)."""
    sc = _validated_site_cells(site_cells)
    keep = np.ones(N_CELLS, bool)
    keep[sc] = False
    nonsite = np.flatnonzero(keep)
    T = int(nonsite.size)
    if not (0 < a_t < T and 0 <= b_t < T):
        raise ValueError(f"(a_t, b_t)=({a_t}, {b_t}) out of range for T={T}")
    if math.gcd(a_t, T) != 1:
        raise ValueError(f"a_t={a_t} not coprime to T={T} — not a bijection")
    j = np.arange(T, dtype=np.int64)
    return nonsite[(a_t * j + b_t) % T]


def encode_tile(user_bits: np.ndarray, rate_id: str, site_cells: np.ndarray,
                a_t: int, b_t: int) -> np.ndarray:
    """One tile: user bits -> (4096,) uint8 cell bits, site cells left 0.

    info = [user | crc32_bits(user) | zeros(n_sites)] (the zero tail = the
    shortened positions), systematic encode, then codeword bit
    transmitted_positions[j] is scattered to cell cell_map[j]."""
    sc = _validated_site_cells(site_cells)
    n_sites = int(sc.size)
    cap = tile_capacity(rate_id, n_sites)
    user = np.asarray(user_bits, np.uint8).ravel()
    if user.size != cap:
        raise ValueError(f"tile takes exactly {cap} user bits, "
                         f"got {user.size}")
    if user.size and int(user.max()) > 1:
        raise ValueError("user_bits must be {0,1}")
    spec = LADDER[rate_id]
    info = np.zeros(spec.k_bits, np.uint8)
    info[:cap] = user
    info[cap:cap + CRC_BITS] = crc32_bits(user)
    cw = encode(info, rate_id)
    cells = np.zeros(N_CELLS, np.uint8)
    cells[cell_map(sc, a_t, b_t)] = cw[transmitted_positions(rate_id,
                                                             n_sites)]
    return cells


@dataclass(frozen=True)
class TileFraming:
    """decode_tile outcome. ok == syndrome_ok AND crc_ok; user_bits is
    None unless ok (never an uncertified payload)."""

    ok: bool
    user_bits: np.ndarray | None
    n_iters: int
    syndrome_ok: bool
    crc_ok: bool


def decode_tile(llr_cells: np.ndarray, rate_id: str, site_cells: np.ndarray,
                a_t: int, b_t: int, max_iters: int = 60,
                alpha: float = 0.8) -> TileFraming:
    """Decode one tile from (4096,) cell LLRs (house convention; 0.0 =
    erasure). Site cells are never read; the shortened info tail is pinned
    -inf (known 0). ok gates on syndrome AND CRC-32. ``alpha`` is the
    normalized-min-sum scaling forwarded to :func:`decode`; receive-side
    callers pass it explicitly so durable attempt identities describe the
    executed decoder (ruling 3.4/§13a)."""
    sc = _validated_site_cells(site_cells)
    n_sites = int(sc.size)
    cap = tile_capacity(rate_id, n_sites)
    x = np.asarray(llr_cells, np.float64).ravel()
    if x.size != N_CELLS:
        raise ValueError(f"llr_cells must be ({N_CELLS},), got {x.shape}")
    spec = LADDER[rate_id]
    llr_code = np.zeros(spec.n_bits)
    llr_code[transmitted_positions(rate_id, n_sites)] = \
        x[cell_map(sc, a_t, b_t)]
    llr_code[spec.k_bits - n_sites:spec.k_bits] = -np.inf   # known 0
    syn_ok, hard, n_iters = decode(llr_code, rate_id, max_iters=max_iters,
                                   alpha=alpha)
    user = hard[:cap].astype(np.uint8)
    crc_ok = bool(np.array_equal(hard[cap:cap + CRC_BITS], crc32_bits(user)))
    ok = bool(syn_ok and crc_ok)
    return TileFraming(ok=ok, user_bits=user if ok else None,
                       n_iters=int(n_iters), syndrome_ok=bool(syn_ok),
                       crc_ok=crc_ok)

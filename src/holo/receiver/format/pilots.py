from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ..lib import bch
from . import keystream

if TYPE_CHECKING:
    from .identity import FormatRow

#: Frozen tile edge (F1).  holo3 spells this substrate constant FOUR
#: times: here and lib/geometry.TILE_CELLS as 64, tile_codec.N_CELLS
#: and identity.N_BITS as 4096.  A change is safe only as a deliberate
#: edit to all four (conversion_docs/04-format-identity.md:48).
TILE_CELLS = 64
#: The exact-100 quota construction: a 10x10 grid on the 64-cell tile,
#: edges floor(i*6.4), spans (6,6,7,6,7,6,6,7,6,7), one site per quota
#: cell in raster order.  The paperholo p60b6 square-quota trick does
#: NOT survive at 64 (conversion_docs/04-format-identity.md:226-238).
N_QUOTA = 10
N_WORD_SITES = N_QUOTA * N_QUOTA
COUNTER_BITS = 18
#: 23 = 18 counter bits + 5 KNOWN-ZERO pads, fixed by BCH(127,50)
#: shortened to (100,23).  The pads are zero so every printed pilot
#: bit is predictable a priori: a data-dependent message bit would
#: flip 39-40 of the 100 sites and poison the correlation template.
PAD_BITS = 5
MESSAGE_BITS = COUNTER_BITS + PAD_BITS
PLANE_K = keystream.PLANE_K

_QUOTA_EDGES = np.array([int(i * TILE_CELLS / N_QUOTA)
                         for i in range(N_QUOTA + 1)], dtype=np.int64)
_QUOTA_SPANS = np.diff(_QUOTA_EDGES)


#: SITE constructions key on the geometry-free sites seed, so
#: equal-density sheets share one measured lattice; VALUE streams key
#: on the ROW seed, which carries the page geometry.  That split IS
#: the identity check (conversion_docs/04-format-identity.md:337-340).
def word_site_cells_yx(sites_seed: bytes) -> np.ndarray:
    q = np.arange(N_WORD_SITES, dtype=np.int64)
    qi, qj = q // N_QUOTA, q % N_QUOTA
    dy = np.empty(N_WORD_SITES, dtype=np.int64)
    dx = np.empty(N_WORD_SITES, dtype=np.int64)
    for span in np.unique(_QUOTA_SPANS):
        sel_y = _QUOTA_SPANS[qi] == span
        dy[sel_y] = keystream.bounded_draws(
            sites_seed, keystream.DOMAIN_PILOT_SITES, 2 * q[sel_y],
            int(span))
        sel_x = _QUOTA_SPANS[qj] == span
        dx[sel_x] = keystream.bounded_draws(
            sites_seed, keystream.DOMAIN_PILOT_SITES, 2 * q[sel_x] + 1,
            int(span))
    return np.stack([_QUOTA_EDGES[qi] + dy, _QUOTA_EDGES[qj] + dx], axis=1)


#: Sequential by construction: the taken-set grows in k, so the ORDER
#: is format law and this loop may be vectorized only within it.  The
#: 16-bit rejection is unbiased because 65536 % 4096 == 0
#: (conversion_docs/04-format-identity.md:239-244, :463).
def filler_site_cells_yx(sites_seed: bytes, n_filler: int,
                         word_cells_yx: np.ndarray) -> np.ndarray:
    if n_filler == 0:
        return np.zeros((0, 2), dtype=np.int64)
    taken = set(map(tuple, word_cells_yx.tolist()))
    out = np.empty((n_filler, 2), dtype=np.int64)
    for k in range(n_filler):
        retry = 0
        placed = False
        while not placed:
            blk = keystream.blocks(sites_seed,
                                   keystream.DOMAIN_FILLER_SITES,
                                   0, 0, k, retry)[0]
            for i in range(0, 16, 2):
                cell = ((int(blk[i]) << 8) | int(blk[i + 1])) % 4096
                yx = (cell // TILE_CELLS, cell % TILE_CELLS)
                if yx not in taken:
                    taken.add(yx)
                    out[k] = yx
                    placed = True
                    break
            retry += 1
            if retry > 64:
                raise RuntimeError("filler rejection runaway")
    return out


def site_cells_yx(sites_seed: bytes, n_filler: int = 0
                  ) -> tuple[np.ndarray, np.ndarray]:
    word = word_site_cells_yx(sites_seed)
    return word, filler_site_cells_yx(sites_seed, n_filler, word)


def site_cell_indices(sites_seed: bytes, n_filler: int = 0) -> np.ndarray:
    word, filler = site_cells_yx(sites_seed, n_filler)
    cells = np.concatenate([word, filler], axis=0)
    flat = cells[:, 0] * TILE_CELLS + cells[:, 1]
    return np.sort(flat)


#: Colour dust POSITIONS deliberately reuse the frozen filler draw
#: under the p120 sites seed — only colour assigns state labels to
#: them.  The stable argsort puts them in canonical physical raster
#: order, which is the order dust values are permuted onto.
def dust_site_cells_yx(sites_seed: bytes,
                       n_dust: int = 20) -> np.ndarray:
    word = word_site_cells_yx(sites_seed)
    dust = filler_site_cells_yx(sites_seed, n_dust, word)
    flat = dust[:, 0] * TILE_CELLS + dust[:, 1]
    return dust[np.argsort(flat, kind="stable")]


def color_site_cells_yx(
    sites_seed: bytes,
) -> tuple[np.ndarray, np.ndarray]:
    return word_site_cells_yx(sites_seed), dust_site_cells_yx(
        sites_seed, 20)


def color_payload_cell_indices(sites_seed: bytes) -> np.ndarray:
    word, dust = color_site_cells_yx(sites_seed)
    furniture = np.concatenate((word, dust), axis=0)
    occupied = np.zeros(TILE_CELLS * TILE_CELLS, dtype=bool)
    occupied[furniture[:, 0] * TILE_CELLS + furniture[:, 1]] = True
    return np.flatnonzero(~occupied).astype(np.int64, copy=False)


#: ONE 100-bit vector, identical for every tile of the row (major=0).
#: The periodicity is load-bearing for cold acquisition: a site-local
#: scramble is removable under any phase hypothesis, before the
#: address is known (conversion_docs/04-format-identity.md:252-254).
def value_scramble_bits(row_seed: bytes, plane: int = PLANE_K) -> np.ndarray:
    return keystream.bits(row_seed, keystream.DOMAIN_PILOT_VALUES, plane,
                          0, np.arange(N_WORD_SITES, dtype=np.int64), 0)


def encode_word(counter: int) -> np.ndarray:
    msg = np.zeros(MESSAGE_BITS, dtype=np.uint8)
    for i in range(COUNTER_BITS):
        msg[i] = (counter >> (COUNTER_BITS - 1 - i)) & 1
    return bch.encode(msg)


def word_values(row_seed: bytes, counters: np.ndarray | list[int] | int,
                plane: int = PLANE_K) -> np.ndarray:
    scr = value_scramble_bits(row_seed, plane)
    counters = np.asarray(counters, dtype=np.int64).ravel()
    out = np.empty((counters.size, N_WORD_SITES), dtype=np.uint8)
    for i, c in enumerate(counters):
        out[i] = encode_word(int(c)) ^ scr
    return out


#: identity imports this module, so the family is asked for at call
#: time: cmy's word law and dust law are its own (CMY-DESIGN §2.5).
def _is_cmy(row: FormatRow) -> bool:
    from .identity import Family
    return row.family is Family.CMY


#: Presence id of Y (C=1 M=2 Y=4): the state cmy's keyed word '0' may
#: print instead of W.
_Y = 4
#: cmy's dust balance: lowest running total first, ties in this order
#: (M, Y, W, C), over the tile's own word supply.
_BALANCE_ORDER: tuple[int, ...] = (2, 4, 0, 1)


#: cmy7/cmy8 print W for '0' and CM for '1'; cmy prints C for '1' and,
#: for '0', W or the Y its site's domain-9 key selects.
def color_word_states(row_seed: bytes,
                      counters: np.ndarray | list[int] | int,
                      row: FormatRow) -> np.ndarray:
    values = word_values(row_seed, counters, PLANE_K)
    zero, one = row.word_states
    states = np.where(values == 1, one, zero).astype(np.uint8)
    if _is_cmy(row):
        for i, c in enumerate(np.asarray(counters, dtype=np.int64).ravel()):
            yellow = keystream.color_word_zero_mask(
                row_seed, int(c), row.n_dust)
            states[i, (values[i] == 0) & yellow] = _Y
    return states


def decode_color_word(states100: np.ndarray, row_seed: bytes,
                      row: FormatRow,
                      erasure_idx: np.ndarray | None = None) -> int | None:
    states = np.asarray(states100)
    zero, one = row.word_states
    lawful = (zero, one, _Y) if _is_cmy(row) else (zero, one)
    if states.shape != (N_WORD_SITES,) or not np.isin(states, lawful).all():
        return None
    return decode_word(
        (states == one).astype(np.uint8), row_seed, PLANE_K,
        erasure_idx=erasure_idx)


def _cycle_dust(cycle: np.ndarray, n_dust: int, counter: int) -> np.ndarray:
    full, extras = divmod(n_dust, cycle.size)
    base = np.tile(cycle, full)
    if extras:
        base = np.concatenate((
            base,
            cycle[[(extras * counter + j) % cycle.size
                   for j in range(extras)]],
        ))
    return base


def _balance_dust(word_states: np.ndarray, n_dust: int) -> np.ndarray:
    totals = [int(np.count_nonzero(word_states == state))
              for state in _BALANCE_ORDER]
    fill = np.empty(n_dust, dtype=np.uint8)
    for i in range(n_dust):
        lowest = totals.index(min(totals))
        fill[i] = _BALANCE_ORDER[lowest]
        totals[lowest] += 1
    return fill


#: The frozen v1 dust law: full cycles in canonical order, then r =
#: n_dust % len(cycle) address-keyed extras at cycle index (r*c+j)%len.
#: At p120 this reproduces the printed record: CMY7 = 4 full cycles,
#: 0 extras; CMY8 = 3 full plus (2c)%6 and (2c+1)%6.  cmy's source
#: vector is the BALANCE law over the tile's own word states instead.
def dust_state_values(row_seed: bytes,
                      counters: np.ndarray | list[int] | int,
                      row: FormatRow) -> np.ndarray:
    cycle = np.asarray(row.dust_base_cycle, dtype=np.uint8)
    n_dust = row.n_dust
    counters = np.asarray(counters, dtype=np.int64).ravel()
    words = (color_word_states(row_seed, counters, row) if _is_cmy(row)
             else None)
    out = np.empty((counters.size, n_dust), dtype=np.uint8)
    for i, counter in enumerate(counters):
        c = int(counter)
        base = (_balance_dust(words[i], n_dust) if words is not None
                else _cycle_dust(cycle, n_dust, c))
        permutation = keystream.color_dust_permutation(row_seed, c, n_dust)
        out[i] = base[permutation]
    return out


def decode_word(values100: np.ndarray, row_seed: bytes,
                plane: int = PLANE_K,
                erasure_idx: np.ndarray | None = None) -> int | None:
    cw = (np.asarray(values100, dtype=np.uint8)
          ^ value_scramble_bits(row_seed, plane))
    res = (bch.decode(cw) if erasure_idx is None
           else bch.decode_erasures(cw, erasure_idx))
    if res is None:
        return None
    msg = res[0][N_WORD_SITES - MESSAGE_BITS:]
    if msg[COUNTER_BITS:].any():
        return None
    counter = 0
    for i in range(COUNTER_BITS):
        counter = (counter << 1) | int(msg[i])
    return counter

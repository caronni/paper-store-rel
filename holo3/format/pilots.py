from __future__ import annotations

import numpy as np

from ..lib import bch
from . import keystream

TILE_CELLS = 64
N_QUOTA = 10
N_WORD_SITES = N_QUOTA * N_QUOTA
COUNTER_BITS = 18
PAD_BITS = 5
MESSAGE_BITS = COUNTER_BITS + PAD_BITS
PLANE_K = keystream.PLANE_K

_QUOTA_EDGES = np.array([int(i * TILE_CELLS / N_QUOTA)
                         for i in range(N_QUOTA + 1)], dtype=np.int64)
_QUOTA_SPANS = np.diff(_QUOTA_EDGES)


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


def color_word_states(row_seed: bytes,
                      counters: np.ndarray | list[int] | int) -> np.ndarray:
    values = word_values(row_seed, counters, PLANE_K)
    return (values * np.uint8(3)).astype(np.uint8, copy=False)


def decode_color_word(states100: np.ndarray, row_seed: bytes,
                      erasure_idx: np.ndarray | None = None) -> int | None:
    states = np.asarray(states100)
    if states.shape != (N_WORD_SITES,) or not np.isin(states, (0, 3)).all():
        return None
    return decode_word(
        (states == 3).astype(np.uint8), row_seed, PLANE_K,
        erasure_idx=erasure_idx)


def dust_state_values(row_seed: bytes,
                      counters: np.ndarray | list[int] | int,
                      dust_base_cycle: tuple[int, ...],
                      n_dust: int) -> np.ndarray:
    cycle = np.asarray(dust_base_cycle, dtype=np.uint8)
    counters = np.asarray(counters, dtype=np.int64).ravel()
    full, extras = divmod(n_dust, cycle.size)
    out = np.empty((counters.size, n_dust), dtype=np.uint8)
    for i, counter in enumerate(counters):
        c = int(counter)
        base = np.tile(cycle, full)
        if extras:
            base = np.concatenate((
                base,
                cycle[[(extras * c + j) % cycle.size
                       for j in range(extras)]],
            ))
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

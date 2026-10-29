"""holo format-v1 pilots: exact-100 colocated sites + BCH address words.

FORMAT-AXIS (HOLO-DESIGN §4.2-§4.3). Every 64x64-cell tile carries the
SAME 100-site pattern (periodicity is load-bearing for cold-start
acquisition: the value scramble is site-local, removable under any phase
hypothesis) and one BCH(127,50,t=13)->(100,23) address word whose message
is the 18-bit flat tile counter plus 5 known-zero pads. All five pads are
zero under the encoding, so every printed pilot bit is predictable a
priori from (row seed, family seed) alone — a data-dependent message bit
would flip 39-40 of the 100 printed sites (measured parity spread,
REASONING-LOG addendum 7) and poison the correlation template.

SITE CONSTRUCTION (the exact-100 quota, normative):
  The tile is divided into a 10x10 grid of quota cells with boundaries
  floor(i*6.4) for i = 0..10 per axis: [0,6,12,19,25,32,38,44,51,57,64]
  (spans 6,6,7,6,7,6,6,7,6,7). Quota cell q = qi*10 + qj (raster order)
  contributes exactly one site:
    dy = bounded_draw(family_seed, DOMAIN_PILOT_SITES, u=2q,   span_y(qi))
    dx = bounded_draw(family_seed, DOMAIN_PILOT_SITES, u=2q+1, span_x(qj))
  site cell = (y0(qi)+dy, x0(qj)+dx); site_index = q. Word codeword bit i
  is printed at site_index i.
  The p60b6 square-quota trick does not survive at 64 — this construction
  replaces it and has its own golden vector + construction battery
  (HOLO-DESIGN §11).

FILLER SITES (density dial above the 2.44 percent floor): F additional
known-value label sites drawn uniformly over the tile's free cells by
16-bit rejection (no bias: 65536 % 4096 == 0), skipping collisions.
v1 registry rows launch at F = 0; quota-izing fillers is open until a
density rung above the floor is actually qualified.

Seeds (HOLO-DESIGN §5.3): the SITE constructions key from the geometry-free
family seed (shared lattice acquisition across rows); the VALUE streams key
from the row seed, which encodes the page geometry — a wrong-geometry
hypothesis descrambles every word to coin flips and refuses at the word
gate.
"""
from __future__ import annotations

import numpy as np

from ..core import bch, channel, keystream
from .profiles import CodecProfile, Family

TILE_CELLS = 64
N_QUOTA = 10                       # 10x10 quota grid -> 100 sites
N_WORD_SITES = N_QUOTA * N_QUOTA
COUNTER_BITS = 18
PAD_BITS = 5
MESSAGE_BITS = COUNTER_BITS + PAD_BITS   # 23, fixed by the BCH code
PLANE_K = keystream.PLANE_K        # 'CMYK'.index('K'), single-sourced

_QUOTA_EDGES = np.array([int(i * TILE_CELLS / N_QUOTA)
                         for i in range(N_QUOTA + 1)], dtype=np.int64)
_QUOTA_SPANS = np.diff(_QUOTA_EDGES)


def word_site_cells_yx(family_seed: bytes) -> np.ndarray:
    """The tile's 100 word-site cells, shape (100, 2) int64 (y, x) in cell
    units, indexed by site_index = quota raster order."""
    q = np.arange(N_WORD_SITES, dtype=np.int64)
    qi, qj = q // N_QUOTA, q % N_QUOTA
    dy = np.empty(N_WORD_SITES, dtype=np.int64)
    dx = np.empty(N_WORD_SITES, dtype=np.int64)
    for span in np.unique(_QUOTA_SPANS):
        sel_y = _QUOTA_SPANS[qi] == span
        dy[sel_y] = keystream.bounded_draws(
            family_seed, keystream.DOMAIN_PILOT_SITES, 2 * q[sel_y],
            int(span))
        sel_x = _QUOTA_SPANS[qj] == span
        dx[sel_x] = keystream.bounded_draws(
            family_seed, keystream.DOMAIN_PILOT_SITES, 2 * q[sel_x] + 1,
            int(span))
    return np.stack([_QUOTA_EDGES[qi] + dy, _QUOTA_EDGES[qj] + dx], axis=1)


def filler_site_cells_yx(family_seed: bytes, n_filler: int,
                         word_cells_yx: np.ndarray) -> np.ndarray:
    """F filler cells, shape (F, 2), collision-free vs word sites and each
    other; deterministic 16-bit rejection scan per filler index."""
    if n_filler == 0:
        return np.zeros((0, 2), dtype=np.int64)
    taken = set(map(tuple, word_cells_yx.tolist()))
    out = np.empty((n_filler, 2), dtype=np.int64)
    for k in range(n_filler):
        retry = 0
        placed = False
        while not placed:
            blk = keystream.blocks(family_seed,
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


def site_cells_yx(family_seed: bytes, n_filler: int = 0
                  ) -> tuple[np.ndarray, np.ndarray]:
    """(word_cells (100,2), filler_cells (F,2)) for the family."""
    word = word_site_cells_yx(family_seed)
    return word, filler_site_cells_yx(family_seed, n_filler, word)


def site_cell_indices(family_seed: bytes, n_filler: int = 0) -> np.ndarray:
    """All site cells as sorted flat indices y*64+x in [0,4096) — the
    shorten set handed to core.ldpc.tile."""
    word, filler = site_cells_yx(family_seed, n_filler)
    cells = np.concatenate([word, filler], axis=0)
    flat = cells[:, 0] * TILE_CELLS + cells[:, 1]
    assert np.unique(flat).size == flat.size
    return np.sort(flat)


def dust_site_cells_yx(family_seed: bytes,
                       n_dust: int = 20) -> np.ndarray:
    """Color dust cells in canonical physical raster order.

    Position construction deliberately reuses the frozen collision-free
    extra-site draw under the new ``p120`` family seed.  Only color assigns
    state labels to those positions.
    """
    word = word_site_cells_yx(family_seed)
    dust = filler_site_cells_yx(family_seed, n_dust, word)
    flat = dust[:, 0] * TILE_CELLS + dust[:, 1]
    return dust[np.argsort(flat, kind="stable")]


def color_site_cells_yx(
    family_seed: bytes,
) -> tuple[np.ndarray, np.ndarray]:
    """The p120 color furniture: 100 indexed word sites and 20 dust."""
    return word_site_cells_yx(family_seed), dust_site_cells_yx(
        family_seed, 20)


def color_payload_cell_indices(family_seed: bytes) -> np.ndarray:
    """Sorted flat indices of the 3,976 non-furniture color cells."""
    word, dust = color_site_cells_yx(family_seed)
    furniture = np.concatenate((word, dust), axis=0)
    occupied = np.zeros(TILE_CELLS * TILE_CELLS, dtype=bool)
    occupied[furniture[:, 0] * TILE_CELLS + furniture[:, 1]] = True
    payload = np.flatnonzero(~occupied).astype(np.int64, copy=False)
    if payload.size != 3976:
        raise AssertionError("p120 color payload-cell arithmetic changed")
    return payload


# ------------------------------------------------------------- word values

def value_scramble_bits(row_seed: bytes, plane: int = PLANE_K) -> np.ndarray:
    """The site-local word-value scramble, one bit per site_index 0..99 —
    identical for every tile (periodic; removable pre-address)."""
    return keystream.bits(row_seed, keystream.DOMAIN_PILOT_VALUES, plane,
                          0, np.arange(N_WORD_SITES), 0)


def encode_word(counter: int) -> np.ndarray:
    """Tile counter -> 100 unscrambled codeword bits (site_index order).
    Message = [counter, 18 bits MSB-first][5 zero pads]."""
    if not 0 <= counter < (1 << COUNTER_BITS):
        raise ValueError("counter out of range")
    msg = np.zeros(MESSAGE_BITS, dtype=np.uint8)
    for i in range(COUNTER_BITS):
        msg[i] = (counter >> (COUNTER_BITS - 1 - i)) & 1
    return bch.encode(msg)


def word_values(row_seed: bytes, counters, plane: int = PLANE_K
                ) -> np.ndarray:
    """Printed word-site values for the given tile counters, shape
    (n_tiles, 100) uint8: BCH(counter) XOR site-local scramble."""
    scr = value_scramble_bits(row_seed, plane)
    counters = np.asarray(counters, dtype=np.int64).ravel()
    out = np.empty((counters.size, N_WORD_SITES), dtype=np.uint8)
    for i, c in enumerate(counters):
        out[i] = encode_word(int(c)) ^ scr
    return out


def color_word_states(row_seed: bytes, counters,
                      codec: CodecProfile) -> np.ndarray:
    """The binary BCH word rendered in the codec's two word states.

    cmy8/cmy7 print W for '0' and CM for '1'.  cmy prints C for '1' and,
    for '0', W or the Y its site's domain-9 key selects
    (``keystream.color_word_zero_mask``).
    """
    values = word_values(row_seed, counters, PLANE_K)
    zero, one = codec.word_states
    states = np.where(values == 1, one, zero).astype(np.uint8)
    if codec.family is Family.CMY:
        for i, c in enumerate(np.asarray(counters, dtype=np.int64).ravel()):
            yellow = keystream.color_word_zero_mask(
                row_seed, int(c), codec.n_dust)
            states[i, (values[i] == 0) & yellow] = channel.CMYState.Y
    return states


def decode_color_word(states100: np.ndarray, row_seed: bytes,
                      codec: CodecProfile,
                      erasure_idx: np.ndarray | None = None) -> int | None:
    """Decode a hard color word on its '1' state; a state outside the
    word's lawful set (the two word states, and Y for cmy) is refused."""
    states = np.asarray(states100)
    zero, one = codec.word_states
    lawful = (zero, one, channel.CMYState.Y) if codec.family is Family.CMY \
        else (zero, one)
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


_BALANCE_ORDER = (channel.CMYState.M, channel.CMYState.Y,
                  channel.CMYState.W, channel.CMYState.C)


def _balance_dust(word_states: np.ndarray, n_dust: int) -> np.ndarray:
    totals = [int(np.count_nonzero(word_states == state))
              for state in _BALANCE_ORDER]
    fill = np.empty(n_dust, dtype=np.uint8)
    for i in range(n_dust):
        lowest = totals.index(min(totals))
        fill[i] = _BALANCE_ORDER[lowest]
        totals[lowest] += 1
    return fill


def dust_state_values(row_seed: bytes, counters,
                      codec: CodecProfile) -> np.ndarray:
    """Known color dust states for concrete physical counters.

    The frozen v1 dust law, stated over the codec's base CYCLE
    (FORMAT-SPACE §5): the source vector is ``n_dust // len(cycle)``
    full cycles in canonical missing-state order, followed by
    ``r = n_dust % len(cycle)`` address-keyed extras at cycle indices
    ``(r*c + j) % len(cycle)`` for ``j < r``.  Domain 9 then permutes
    that vector onto the dust sites in canonical physical raster order.

    At the frozen p120 rows this reproduces the printed record
    bit-exactly: CMY7 (cycle 5, dust 20) is four full cycles with no
    extras; CMY8 (cycle 6, dust 20) is three full cycles plus the two
    extras ``(2c) % 6, (2c + 1) % 6``.

    cmy's source vector is the BALANCE law instead: from the tile's own
    word supply (its C, W and Y counts; M none), each dust site in turn
    goes to the state with the lowest running total, ties M, Y, W, C.
    """
    cycle = np.asarray(codec.dust_base_cycle, dtype=np.uint8)
    n_dust = codec.n_dust
    balance = codec.family is Family.CMY
    if n_dust == 0 or (cycle.size == 0 and not balance):
        raise ValueError(f"{codec.codec_id}: codec has no color dust schedule")

    counters = np.asarray(counters, dtype=np.int64).ravel()
    if counters.size and (
            int(counters.min()) < 0
            or int(counters.max()) >= (1 << COUNTER_BITS)):
        raise ValueError("color dust tile counter out of range")
    words = color_word_states(row_seed, counters, codec) if balance else None
    out = np.empty((counters.size, n_dust), dtype=np.uint8)
    for i, counter in enumerate(counters):
        c = int(counter)
        base = (_balance_dust(words[i], n_dust) if balance
                else _cycle_dust(cycle, n_dust, c))
        permutation = keystream.color_dust_permutation(row_seed, c, n_dust)
        out[i] = base[permutation]
    return out


def decode_word(values100: np.ndarray, row_seed: bytes,
                plane: int = PLANE_K,
                erasure_idx: np.ndarray | None = None) -> int | None:
    """Descramble + BCH decode + pad gate. Returns the counter, or None
    on refusal (decode failure, nonzero pads). erasure_idx: unreliable
    site positions (0..99), budget 2e+f<=26 enforced inside bch."""
    cw = (np.asarray(values100, dtype=np.uint8)
          ^ value_scramble_bits(row_seed, plane))
    res = (bch.decode(cw) if erasure_idx is None
           else bch.decode_erasures(cw, erasure_idx))
    if res is None:
        return None
    msg = bch.message_from_word(res[0])
    if msg[COUNTER_BITS:].any():          # the 2^-5 known-zero pad gate
        return None
    counter = 0
    for i in range(COUNTER_BITS):
        counter = (counter << 1) | int(msg[i])
    return counter

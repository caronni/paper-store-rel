"""Synthetic cmy8 tile-streams for the W1c tests (no run dir, no pixels).

A frame is built the way the printer builds one — `encode_frame` for a real
FormatRow and bank, XOR the real dither, project through the real cell
permutation onto the tile's payload cells — and then read back exactly the way
`tiles._sequential_payload` reads one, so the tests exercise the same domain
the analyzer will meet on paper.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import ndtri

from holo3.format import keystream, tile_codec
from holo3.format.identity import build_site_geometry, resolve_format_ref
from holo3.lib import ldpc
from holo3.lib.ldpc import CODES
from holo3.plugins.tiles import stream_fact

R0850 = "L:c2-cmy8-r0850-p120-x1@3392x2368"
R0700 = "L:c2-cmy8-r0700-p120-x1@3392x2368"

AMPLITUDE = 3.0
_ROWS: dict[str, object] = {}


def row_of(ref: str):
    cached = _ROWS.get(ref)
    if cached is None:
        cached = resolve_format_ref(ref)
        _ROWS[ref] = cached
    return cached


@dataclass(frozen=True)
class Frame:
    ref: str
    row: object
    key: tuple[int, int, int, str]
    bank: tuple
    user: np.ndarray
    dither: np.ndarray
    printed: np.ndarray          # as-printed SEQUENTIAL bits (payload_cells,)
    codeword: np.ndarray         # mother-domain GT codeword (n_bits,)
    active: int


def build_frame(ref: str = R0850, key=(0, 12, 7, "C"), *, seed: int = 7
                ) -> Frame:
    row = row_of(ref)
    fact = stream_fact(row, key[3])
    bank = fact.rung_children
    code_id, shorten = bank[0]
    code = CODES[code_id]
    active = code.k_bits - shorten
    counter = row.tile_counter(*key[:3])
    user = np.random.default_rng(seed).integers(
        0, 2, fact.user_bits, dtype=np.uint8)
    dither = keystream.cmy8_dither_bits(row.seed, key[3], counter,
                                        row.payload_cells)
    printed = tile_codec.encode_frame(user, bank) ^ dither
    info = np.zeros(code.k_bits, np.uint8)
    info[:active] = np.concatenate((user, tile_codec.crc32_bits(user)))
    codeword = ldpc.encode(info, code)
    return Frame(ref=ref, row=row, key=key, bank=bank, user=user,
                 dither=dither, printed=printed, codeword=codeword,
                 active=active)


def through_cells(frame: Frame) -> np.ndarray:
    """Print the frame onto the tile's cells and read it back sequentially.

    Mirrors `color_sites.certified_projection` (write) and
    `tiles._sequential_payload` (read); the identity is the point.
    """
    row = frame.row
    counter = row.tile_counter(*frame.key[:3])
    geometry = build_site_geometry(row)
    payload_flat = np.asarray(geometry.payload_flat, np.int64)
    order = keystream.color_cell_permutation(row.seed, counter,
                                             row.payload_cells)
    cells = np.zeros(tile_codec.N_CELLS, np.uint8)
    cells[payload_flat] = frame.printed[order]
    physical = cells[payload_flat]
    sequential = np.empty(row.payload_cells, np.uint8)
    sequential[order] = physical
    return sequential


def sigma_for(hard_error: float) -> float:
    """Noise sigma giving `hard_error` sign flips on a +-AMPLITUDE signal."""
    return AMPLITUDE / float(-ndtri(hard_error))


def channel_llr(bits: np.ndarray, hard_error: float, seed: int
                ) -> np.ndarray:
    """A calibrated bi-AWGN LLR: y ~ N(+-A, sigma^2), LLR = 2*A*y/sigma^2."""
    sigma = sigma_for(hard_error)
    rng = np.random.default_rng(seed)
    y = AMPLITUDE * (2.0 * np.asarray(bits, np.float64) - 1.0)
    y = y + rng.normal(0.0, sigma, y.size)
    return (2.0 * AMPLITUDE / sigma ** 2) * y


def hard_error_of(llr: np.ndarray, bits: np.ndarray) -> float:
    return float(np.mean((llr > 0) != (np.asarray(bits) > 0)))


def near_codeword_llr(frame: Frame, n_bad: int, seed: int, *,
                      base_hard: float = 0.02, scale: float = 0.5
                      ) -> np.ndarray:
    """A thin-margin channel with `n_bad` confidently MISREAD cells.

    MEASURED (2026-09-03, r0850): plain bi-AWGN never produces the regime
    L4 targets — 590 decodes over 13 noise levels gave 0 exits with
    1 <= unsat <= 12, which is the bimodality the DESIGN §6 deferral rule
    quotes.  What does produce it is the failure the real residue has: a
    tile whose evidence is weak everywhere (`scale`) and confidently WRONG
    on a few cells (a misregistered or occluded burst).  BP then settles
    one or two bits away from the codeword, and since r0850's variable
    degree is at most 6, that is an exit at 3-12 unsatisfied checks — sheet
    H's own 5-9 shoulder.
    """
    llr = channel_llr(frame.printed, base_hard, seed=2500 + seed * 97) * scale
    rng = np.random.default_rng(seed * 613 + n_bad * 29)
    bad = rng.choice(llr.size, n_bad, replace=False)
    llr = llr.copy()
    llr[bad] = -(2.0 * frame.printed[bad].astype(np.float64) - 1.0) * \
        ldpc.LLR_CLIP
    return llr

from __future__ import annotations

import functools
import math
from dataclasses import dataclass

import numpy as np

from ..format import keystream, pilots
from ..format.identity import Family, FormatRow
from ..lib import bch

#: The per-phase visibility floor on the 100 word sites, applied to the
#: SURVIVING candidate after the BCH decode - not a window mask gate.
#: Hidden samples never become erasures at this cold rung: the Stage-A
#: false-accept budget is derived for full-support words (spec 01 §4).
STAGE_A_MIN_VISIBLE_SITES: int = 90
#: The family-wise false-accept target for the whole Stage-A sweep, and
#: it is PROVISIONAL: the historical E021-E023c stand-in that v1 carried
#: as _PROVISIONAL_ALPHA under the qualification id
#: 'holo-v1/e022-single-word-multi-slot-union-bound'.  Not frozen.
WORD_FALSE_ACCEPT: float = 1e-3
#: The union-bound term: a random 100-bit word lands within radius 13 of
#: one of the 2^18 pad-valid counter codewords with probability 1.72e-9.
#: A 200-cell window declares 147,456 hypotheses and so spends 2.5e-4 of
#: the budget; the bound assumes nothing about overlapping phases.
SINGLE_WORD_PROBABILITY: float = math.ldexp(
    float(sum(math.comb(pilots.N_WORD_SITES, errors)
              for errors in range(bch.T + 1))),
    pilots.COUNTER_BITS - pilots.N_WORD_SITES)
#: Ink components per CMY state.  Addressing reads equal-channel luma,
#: so the dust reference splits at >= 2 inks: under the provisional ideal
#: subtractive renderer that is exactly the pinned 50/50 dark half (four
#: of the eight states), which is all a blind reference can assert.
INK_COUNT: tuple[int, ...] = (0, 1, 1, 2, 1, 2, 2, 3)
_LUMA_DARK: frozenset[int] = frozenset(
    state for state, ink in enumerate(INK_COUNT) if ink >= 2)
#: The dust states the addressing reference reads as dark, per colour
#: family.  cmy reads the sites AS LAID in R (R7, R24): C is dark there,
#: W, Y and M light, so its dark set is {C} -- a luma split would misread
#: its C-on-W/Y words.
ADDRESSING_DARK: dict[Family, frozenset[int]] = {
    Family.CMY7: _LUMA_DARK, Family.CMY8: _LUMA_DARK,
    Family.CMY: frozenset({1})}
#: The families whose addressing reads the R plane (planes[0]) instead of
#: equal-channel luma: placement's crop, the platen backing and the split.
ADDRESSING_ON_R: frozenset[Family] = frozenset({Family.CMY})


#: The expected fraction of a tile's cells addressing reads as dark:
#: payload states uniform (every stream is keystream-dithered), word sites
#: half '1', and the dust as tile counter 0 lays it.
@functools.cache
def addressing_dark_fraction(row: FormatRow) -> float:
    dark = ADDRESSING_DARK[row.family]
    payload = (row.payload_cells * len(dark.intersection(row.state_ids))
               / len(row.state_ids))
    word_sites = pilots.N_WORD_SITES * sum(
        state in dark for state in row.word_states) / 2
    dust = int(np.isin(pilots.dust_state_values(row.seed, (0,), row),
                       sorted(dark)).sum())
    return ((payload + word_sites + dust)
            / (pilots.TILE_CELLS * pilots.TILE_CELLS))


#: The addressing midpoint over sampled values.  The luma families keep
#: np.median EXACTLY (np.quantile(., 0.5) is not bit-identical to it).  A
#: family read on R has {C}, a quarter of the cells, dark: it splits
#: midway between the dark and the light population's medians, the
#: quantiles at f/2 and (1+f)/2 of the row's dark fraction f, which sits
#: between the clusters for any window dark share d in (f/2, (1+f)/2).
#: At p120 f = (3976·¼ + 100·½ + 0)/4096 = 0.25488 (payload uniform over
#: four states, word '1' = C at half the sites, no C in the dust), so d
#: in (0.127, 0.627).  The bare quantile at f (cmy8's median is the bare
#: quantile at 0.5) misreads only the ~|d − f|·N tail cells once noise
#: breaks ties.  Its 495 of 1,174 word and dust sites wrong on the clean
#: c3 sim (A2, 2026-10-12, a window 0.3 points over f) was a TIE
#: artifact: that page's R takes exactly four values, {50, 217, 230, 231}
#: then (C 51 since the bars were rounded), the quantile at f lands ON
#: C's value and the strict `<` reads every C cell light.
def addressing_split(values: np.ndarray, row: FormatRow) -> float:
    if row.family in ADDRESSING_ON_R:
        dark = addressing_dark_fraction(row)
        low, high = np.quantile(values, (dark / 2.0, (1.0 + dark) / 2.0))
        return float(0.5 * (low + high))
    return float(np.median(values))

#: The v0.26 staged sweep (RECEIVE-DESIGN ledger): decode the historical
#: centre slot first, the rest only if the centre yields no passing seed.
#: Measured per window on the word-succeeding path 3,627 -> 794 ms at
#: identical yield: the all-slot sweep cost +267 s CPU for 604 certs.
STAGE_ALL: str = "all"
STAGE_CENTRE: str = "centre"
STAGE_REST: str = "rest"


#: Colour rows scramble with the K plane because the printed colour word
#: IS the K word in a two-state alphabet: pilots.color_word_states renders
#: the row's word pair over word_values(seed, counters, PLANE_K) — W/CM for
#: cmy7 and cmy8, C against the keyed W/Y for cmy (R10).  One luma addressing
#: pass serves every plane of cmy7/cmy8; cmy addresses on R (R24); per-plane
#: poses are an arm on top.
def addressing_plane(row: FormatRow) -> int:
    if row.family is Family.K:
        return row.streams[0].plane
    return pilots.PLANE_K


@dataclass(frozen=True)
class ReferencePage:
    page: int
    values: np.ndarray
    sites: np.ndarray


def _site_cells(row: FormatRow) -> tuple[np.ndarray, np.ndarray]:
    if row.family is Family.K:
        return pilots.site_cells_yx(
            row.sites_seed, row.n_sites - pilots.N_WORD_SITES)
    return (pilots.word_site_cells_yx(row.sites_seed),
            pilots.dust_site_cells_yx(row.sites_seed, row.n_dust))


def _site_mask(row: FormatRow) -> np.ndarray:
    tiles_y, tiles_x = row.tiles_yx
    height, width = row.cells_yx
    word_cells, extra_cells = _site_cells(row)
    tile_indices = np.arange(tiles_y * tiles_x, dtype=np.int64)
    tile_y = tile_indices // tiles_x
    tile_x = tile_indices % tiles_x
    sites = np.zeros((height, width), bool)
    word_y = tile_y[:, None] * pilots.TILE_CELLS + word_cells[None, :, 0]
    word_x = tile_x[:, None] * pilots.TILE_CELLS + word_cells[None, :, 1]
    sites[word_y, word_x] = True
    if extra_cells.size:
        extra_y = tile_y[:, None] * pilots.TILE_CELLS + extra_cells[None, :, 0]
        extra_x = tile_x[:, None] * pilots.TILE_CELLS + extra_cells[None, :, 1]
        sites[extra_y, extra_x] = True
    return sites


def reference_page(row: FormatRow, page: int,
                   sites: np.ndarray | None = None) -> ReferencePage:
    tiles_y, tiles_x = row.tiles_yx
    height, width = row.cells_yx
    color = row.family is not Family.K
    word_cells, extra_cells = _site_cells(row)
    tile_indices = np.arange(tiles_y * tiles_x, dtype=np.int64)
    tile_y = tile_indices // tiles_x
    tile_x = tile_indices % tiles_x
    counters = page * (tiles_y * tiles_x) + tile_indices
    words = pilots.word_values(row.seed, counters, addressing_plane(row))
    values = np.zeros((height, width), np.uint8)
    word_y = tile_y[:, None] * pilots.TILE_CELLS + word_cells[None, :, 0]
    word_x = tile_x[:, None] * pilots.TILE_CELLS + word_cells[None, :, 1]
    values[word_y, word_x] = words
    if extra_cells.size:
        extra_y = tile_y[:, None] * pilots.TILE_CELLS + extra_cells[None, :, 0]
        extra_x = tile_x[:, None] * pilots.TILE_CELLS + extra_cells[None, :, 1]
        if color:
            dark = np.zeros(len(INK_COUNT), np.uint8)
            dark[sorted(ADDRESSING_DARK[row.family])] = 1
            states = pilots.dust_state_values(row.seed, counters, row)
            values[extra_y, extra_x] = dark[states]
        else:
            values[extra_y, extra_x] = keystream.bits(
                row.seed, keystream.DOMAIN_FILLER_VALUES,
                row.streams[0].plane, page, extra_y, extra_x,
            ).reshape(extra_y.shape)
    if sites is None:
        sites = _site_mask(row)
    return ReferencePage(page, values, sites)


#: Pages materialize on FIRST TOUCH.  One page of reference values is
#: MiB-scale and the possible domain runs from 133 pages at 53x37 to
#: 5,349 at 7x7, so the whole-domain warm-up was deleted with the dynamic
#: page domain (2026-09-01) rather than paid for up front.
class ReferenceField:
    def __init__(self, row: FormatRow) -> None:
        self.row = row
        self.cells_yx = row.cells_yx
        self._sites = _site_mask(row)
        self._pages: dict[int, ReferencePage] = {}

    def page(self, page: int) -> ReferencePage:
        cached = self._pages.get(page)
        if cached is None:
            cached = reference_page(self.row, page, self._sites)
            self._pages[page] = cached
        return cached


@dataclass(frozen=True)
class WordCandidate:
    oriented_origin_yx: tuple[int, int]
    rot_k: int
    counter: int
    page: int
    tile_yx: tuple[int, int]
    errors: int
    page_origin_yx: tuple[int, int]
    visible: int = 0


_SITE_INDEX_CACHE: dict[bytes, np.ndarray] = {}


def word_site_index(sites_seed: bytes) -> np.ndarray:
    cached = _SITE_INDEX_CACHE.get(sites_seed)
    if cached is None:
        cached = np.full((pilots.TILE_CELLS, pilots.TILE_CELLS), -1, np.int16)
        positions = pilots.word_site_cells_yx(sites_seed)
        cached[positions[:, 0], positions[:, 1]] = np.arange(
            positions.shape[0], dtype=np.int16)
        cached.flags.writeable = False
        _SITE_INDEX_CACHE[sites_seed] = cached
    return cached


def _slot_grid(shape: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    height, width = shape
    period = pilots.TILE_CELLS
    if height < period or width < period:
        return ()
    return tuple(
        (row, col)
        for row in range((height - period) // period + 1)
        for col in range((width - period) // period + 1))


#: Every slot is DECLARED at the base slot's phase room, so the trailing
#: row and column over-declare.  That is deliberate: the union bound only
#: needs the declaration to dominate the attempts actually made, and a
#: tightened count would have to be re-qualified.
def _slot_phase_capacity(shape: tuple[int, int]) -> int:
    height, width = shape
    period = pilots.TILE_CELLS
    if height < period or width < period:
        return 0
    return min(period, height - period + 1) * min(period, width - period + 1)


def _centre_slot(shape: tuple[int, int]) -> tuple[int, int] | None:
    grid = _slot_grid(shape)
    if not grid:
        return None
    period = pilots.TILE_CELLS
    height, width = shape
    return min(
        grid,
        key=lambda slot: (
            abs(slot[0] * period + period - height / 2)
            + abs(slot[1] * period + period - width / 2),
            slot,
        ))


def _slot_phase_shape(shape: tuple[int, int],
                      slot: tuple[int, int]) -> tuple[int, int]:
    height, width = shape
    period = pilots.TILE_CELLS
    base_y, base_x = slot[0] * period, slot[1] * period
    return (min(period, height - base_y - period + 1),
            min(period, width - base_x - period + 1))


def stage_a_hypotheses(shape: tuple[int, int]) -> int:
    oriented = (int(shape[0]), int(shape[1]))
    total = 0
    for rot_k in range(4):
        shape_k = oriented if rot_k % 2 == 0 else (oriented[1], oriented[0])
        total += len(_slot_grid(shape_k)) * _slot_phase_capacity(shape_k)
    return total


@dataclass(frozen=True)
class _SlotGather:
    words: np.ndarray
    visible: np.ndarray
    origins_y: np.ndarray
    origins_x: np.ndarray


def _gather_slot(grid: np.ndarray, mask: np.ndarray, shape: tuple[int, int],
                 slot: tuple[int, int],
                 positions: np.ndarray) -> _SlotGather | None:
    period = pilots.TILE_CELLS
    base_y, base_x = slot[0] * period, slot[1] * period
    row_limit, col_limit = _slot_phase_shape(shape, slot)
    if row_limit <= 0 or col_limit <= 0:
        return None
    phase_y = np.arange(row_limit)
    phase_x = np.arange(col_limit)
    iy = base_y + phase_y[:, None] + positions[None, :, 0]
    ix = base_x + phase_x[:, None] + positions[None, :, 1]
    values = grid[iy[:, None, :], ix[None, :, :]]
    visible = mask[iy[:, None, :], ix[None, :, :]]
    return _SlotGather(
        values.reshape(-1, positions.shape[0]),
        visible.reshape(-1, positions.shape[0]),
        base_y + np.repeat(phase_y, col_limit),
        base_x + np.tile(phase_x, row_limit))


def _word_candidate(corrected: np.ndarray, errors: int, row: FormatRow,
                    rot_k: int, origin: tuple[int, int],
                    visible: int = 0) -> WordCandidate | None:
    message = bch.message_from_word(corrected)
    if message[pilots.COUNTER_BITS:].any():
        return None
    counter = 0
    for bit in message[:pilots.COUNTER_BITS]:
        counter = (counter << 1) | int(bit)
    page, tile_y, tile_x = row.tile_address(counter)
    if page >= row.max_pages:
        return None
    # errors IS the printed-word Hamming distance: XOR by the fixed
    # scramble preserves distance, and the accepted zero-pad message
    # re-encodes to `corrected`.  So this compares like with like.
    errors = int(errors)
    if errors > bch.T:
        return None
    page_origin = (tile_y * pilots.TILE_CELLS - origin[0],
                   tile_x * pilots.TILE_CELLS - origin[1])
    return WordCandidate(
        origin, rot_k, int(counter), int(page),
        (int(tile_y), int(tile_x)), errors, page_origin, int(visible))


def _decode_candidates(bits: np.ndarray, mask: np.ndarray, row: FormatRow,
                       stage: str) -> tuple[WordCandidate, ...]:
    positions = pilots.word_site_cells_yx(row.sites_seed)
    scramble = pilots.value_scramble_bits(row.seed, addressing_plane(row))
    keyed: list[tuple[tuple[int, int, int, int], WordCandidate]] = []
    for rot_k in range(4):
        oriented_bits = np.rot90(np.asarray(bits, np.uint8), rot_k)
        oriented_mask = np.rot90(np.asarray(mask, bool), rot_k)
        shape = (int(oriented_bits.shape[0]), int(oriented_bits.shape[1]))
        centre = _centre_slot(shape)
        for slot_index, slot in enumerate(_slot_grid(shape)):
            if stage == STAGE_CENTRE and slot != centre:
                continue
            if stage == STAGE_REST and slot == centre:
                continue
            gathered = _gather_slot(
                oriented_bits, oriented_mask, shape, slot, positions)
            if gathered is None:
                continue
            decoded = bch.decode_many(gathered.words ^ scramble)
            for phase_index, result in enumerate(decoded):
                visible = int(np.count_nonzero(gathered.visible[phase_index]))
                if result is None or visible < STAGE_A_MIN_VISIBLE_SITES:
                    continue
                origin = (int(gathered.origins_y[phase_index]),
                          int(gathered.origins_x[phase_index]))
                candidate = _word_candidate(
                    result[0], result[1], row, rot_k, origin, visible)
                if candidate is None:
                    continue
                keyed.append((
                    (candidate.errors, slot_index, rot_k, phase_index),
                    candidate))
    # ONE errors-first trial order across every orientation and every slot
    # this stage decodes: a clean rot1 seed precedes a 13-error rot0 seed.
    # Ties break deterministically by oriented slot index, then rot_k, then
    # the slot's row-major phase, so worker count cannot move the answer.
    keyed.sort(key=lambda entry: entry[0])
    return tuple(candidate for _key, candidate in keyed)


@dataclass(frozen=True)
class StageAResult:
    candidates: tuple[WordCandidate, ...]
    hypotheses: int
    reason: str


def stage_a(bits: np.ndarray, mask: np.ndarray, row: FormatRow,
            stage: str = STAGE_ALL) -> StageAResult:
    samples = np.asarray(bits, np.uint8)
    visibility = np.asarray(mask, bool)
    # The declared domain is the FULL multi-slot ceiling whatever `stage`
    # actually decodes, so the budget refusal is the same for centre, rest
    # and all: a stage that sweeps fewer slots under the same declaration is
    # conservative under the union bound, never cheaper in false accepts.
    hypotheses = stage_a_hypotheses(
        (int(samples.shape[0]), int(samples.shape[1])))
    if hypotheses * SINGLE_WORD_PROBABILITY > WORD_FALSE_ACCEPT:
        return StageAResult((), hypotheses, "attempt_budget_exceeded")
    candidates = _decode_candidates(samples, visibility, row, stage)
    return StageAResult(
        candidates, hypotheses,
        "candidates" if candidates else "no_word_candidate")


#: Two rival populations, both the word route's own: the other decoded
#: candidates minus the winner's own neighbourhood (same page and rot
#: within the radius is the SAME answer), plus the winner's rectangle on
#: every other possible page - the alias the word decode cannot see.
def word_rival_rows(
    winner: WordCandidate,
    candidates: tuple[WordCandidate, ...],
    page_domain: tuple[int, ...],
    radius: int,
) -> tuple[tuple[int, tuple[int, int], int], ...]:
    identity = (winner.page, winner.page_origin_yx, winner.rot_k)
    rows: list[tuple[int, tuple[int, int], int]] = []
    seen = {identity}
    for candidate in candidates:
        row_id = (candidate.page, candidate.page_origin_yx, candidate.rot_k)
        if row_id in seen:
            continue
        if (candidate.page == winner.page
                and candidate.rot_k == winner.rot_k
                and max(abs(candidate.page_origin_yx[0]
                            - winner.page_origin_yx[0]),
                        abs(candidate.page_origin_yx[1]
                            - winner.page_origin_yx[1])) <= radius):
            continue
        seen.add(row_id)
        rows.append(row_id)
    # The domain here is the POSSIBLE page set, never the live set: word
    # admission opens pages, so a marginal word must be scored against the
    # pages it could have named, or it instantiates a phantom one.
    for page in page_domain:
        row_id = (int(page), winner.page_origin_yx, winner.rot_k)
        if row_id in seen:
            continue
        seen.add(row_id)
        rows.append(row_id)
    return tuple(rows)

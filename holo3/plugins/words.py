from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..format import keystream, pilots
from ..format.identity import Family, FormatRow
from ..lib import bch

STAGE_A_MIN_VISIBLE_SITES: int = 90
WORD_FALSE_ACCEPT: float = 1e-3
SINGLE_WORD_PROBABILITY: float = math.ldexp(
    float(sum(math.comb(pilots.N_WORD_SITES, errors)
              for errors in range(bch.T + 1))),
    pilots.COUNTER_BITS - pilots.N_WORD_SITES)
INK_COUNT: tuple[int, ...] = (0, 1, 1, 2, 1, 2, 2, 3)

STAGE_ALL: str = "all"
STAGE_CENTRE: str = "centre"
STAGE_REST: str = "rest"


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
    return pilots.color_site_cells_yx(row.sites_seed)


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
            states = pilots.dust_state_values(
                row.seed, counters, row.dust_base_cycle, row.n_dust)
            ink = np.asarray(INK_COUNT, np.uint8)
            values[extra_y, extra_x] = (ink[states] >= 2).astype(np.uint8)
        else:
            values[extra_y, extra_x] = keystream.bits(
                row.seed, keystream.DOMAIN_FILLER_VALUES,
                row.streams[0].plane, page, extra_y, extra_x,
            ).reshape(extra_y.shape)
    if sites is None:
        sites = _site_mask(row)
    return ReferencePage(page, values, sites)


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
    hypotheses = stage_a_hypotheses(
        (int(samples.shape[0]), int(samples.shape[1])))
    if hypotheses * SINGLE_WORD_PROBABILITY > WORD_FALSE_ACCEPT:
        return StageAResult((), hypotheses, "attempt_budget_exceeded")
    candidates = _decode_candidates(samples, visibility, row, stage)
    return StageAResult(
        candidates, hypotheses,
        "candidates" if candidates else "no_word_candidate")


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
    for page in page_domain:
        row_id = (int(page), winner.page_origin_yx, winner.rot_k)
        if row_id in seen:
            continue
        seen.add(row_id)
        rows.append(row_id)
    return tuple(rows)

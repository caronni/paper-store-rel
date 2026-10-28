from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import replace as dc_replace
from fractions import Fraction
from typing import Iterable, Sequence

import numpy as np

from ..data import (
    AttemptFact,
    Certificate,
    ColorEvidenceRow,
    IntegrityError,
    JobResult,
    TileOutcome,
    WindowEvidence,
)
from ..descriptor import (
    FactKey,
    Job,
    KEY_COLOR_ROW,
    KEY_EVIDENCE_FIT,
    KEY_EVIDENCE_READ,
    PluginDescriptor,
    Subject,
)
from ..format import keystream, pilots, tile_codec
from ..format.identity import (
    Family, FormatRow, SiteGeometry, StreamFact, scramble_plane)
from ..lib.geometry import (
    TILE_CELLS,
    apply_affine,
    invert_affine,
    tile_of_cell,
)
from ..lib.ldpc import CODES
from ..lib.owners import freeze_page_owners

BASELINE_BP_MAX_ITERS: int = 60
RETRY_BP_MAX_ITERS: int = 150
BP_ALPHA: float = 0.8

STAGE_SCAN: str = "scan"
STAGE_UNION: str = "union"
STAGE_RETRY150: str = "retry150"
STAGE_LOCAL150: str = "local150"
# the supplemental residue stages (plugins/uplift.py). Like local150
# they are attempt stages, not tile rows: the tile vocabulary and the BP
# budget law stay defined in one place, so a heavy stage cannot drift
# from its budget.
STAGE_UPLIFT_A3: str = "uplift_a3"
STAGE_UPLIFT_A4B: str = "uplift_a4b"
# the plane-isolated residue stage (plugins/plane_k.py): one cmy8 plane
# read as a black-and-white page and decoded as its own stream.
STAGE_PLANEK150: str = "planek150"
# the per-plane local-affine rescue (plugins/swim.py), same law again
STAGE_SWIM150: str = "swim150"
ORDINARY_STAGES: tuple[str, str] = (STAGE_SCAN, STAGE_UNION)
HEAVY_STAGES: frozenset[str] = frozenset(
    {STAGE_RETRY150, STAGE_LOCAL150, STAGE_UPLIFT_A3, STAGE_UPLIFT_A4B,
     STAGE_PLANEK150, STAGE_SWIM150})

STAGE_PAYLOAD: str = "payload"
PAYLOAD_COST: int = 20
RUNG_COST: int = 2
PRICES: tuple[tuple[str, int], ...] = ((STAGE_PAYLOAD, PAYLOAD_COST),)

OUTCOME_BELOW_FLOOR: str = "below_attempt_floor"
OUTCOME_FAILED: str = "attempted_failed"
OUTCOME_CERTIFIED: str = "certified"

PLUGIN: str = "tiles"
N_CELLS: int = tile_codec.N_CELLS
ARITY_BY_FAMILY: dict[Family, int] = {
    Family.K: 1, Family.CMY7: 6, Family.CMY8: 3}

TileKey = tuple[int, int, int, str]
TileAddress = tuple[int, int, int]
Bank = tuple[tuple[str, int], ...]
DonePose = tuple[int, tuple[int, int, int, int], tuple[float, ...]]
CoverKey = tuple[int, int, int, str, int]
ColorRowKey = tuple[str, int, int, int]


@dataclass(frozen=True)
class TileCut:
    capture_id: str
    level_index: int
    page: int
    ty: int
    tx: int
    values: np.ndarray
    observed_flat: np.ndarray


@dataclass(frozen=True)
class TileAttemptResult:
    fact: AttemptFact
    certificate: Certificate | None
    event: TileOutcome


def evidence_arity(row: FormatRow) -> int:
    return ARITY_BY_FAMILY[row.family]


def source_tag(stage: str) -> str:
    return f"{PLUGIN}/{stage}"


def max_iters_for(stage: str) -> int:
    return RETRY_BP_MAX_ITERS if stage in HEAVY_STAGES \
        else BASELINE_BP_MAX_ITERS


def stream_fact(row: FormatRow, stream_id: str) -> StreamFact:
    return next(fact for fact in row.streams if fact.stream_id == stream_id)


def k_eff_bits(row: FormatRow) -> int:
    rate_id, _shorten = row.streams[0].rung_children[0]
    return CODES[rate_id].k_bits - row.n_sites


def _bank_active_bits(bank: Bank) -> int:
    return sum(CODES[code_id].k_bits - shorten for code_id, shorten in bank)


def _bank_transmitted_bits(bank: Bank) -> int:
    return sum(CODES[code_id].n_bits - shorten for code_id, shorten in bank)


def _children_meet_floor(values: np.ndarray, bank: Bank) -> bool:
    offset = 0
    result = True
    for code_id, shorten in bank:
        code = CODES[code_id]
        stop = offset + code.n_bits - shorten
        supported = int(np.count_nonzero(values[offset:stop]))
        result = result and supported >= code.k_bits - shorten
        offset = stop
    return result


def _site_mask_yx(geometry: SiteGeometry) -> np.ndarray:
    mask = np.zeros(N_CELLS, dtype=bool)
    mask[np.asarray(geometry.shorten_flat, dtype=np.int64)] = True
    return mask.reshape(TILE_CELLS, TILE_CELLS)


def _tile_scramble_bits(row: FormatRow, geometry: SiteGeometry, page: int,
                        ty: int, tx: int,
                        site_mask_yx: np.ndarray) -> np.ndarray:
    plane = scramble_plane(row, geometry, page)
    tile = plane[ty * TILE_CELLS:(ty + 1) * TILE_CELLS,
                 tx * TILE_CELLS:(tx + 1) * TILE_CELLS]
    return (tile & ~site_mask_yx).astype(np.uint8, copy=False)


def evidence_cover_cells(lookup: object,
                         page_cells_yx: np.ndarray) -> np.ndarray:
    from . import calibrate

    cells = np.asarray(page_cells_yx, np.int64)
    return cells[calibrate.payload_cell_mask(lookup, cells)]


def color_cover_cells(geometry: SiteGeometry,
                      page_cells_yx: np.ndarray) -> np.ndarray:
    from . import color_region

    cells = np.asarray(page_cells_yx, np.int64)
    return cells[color_region.cargo_row_indices(geometry, cells)]


def cover_keys(page: int, cells_yx: np.ndarray, capture_id: str,
               level_index: int) -> tuple[CoverKey, ...]:
    cells = np.asarray(cells_yx, np.int64)
    if not cells.shape[0]:
        return ()
    ty, tx = tile_of_cell(cells[:, 0], cells[:, 1])
    pairs = np.unique(np.stack((ty, tx), axis=1), axis=0)
    return tuple((page, int(pair[0]), int(pair[1]), capture_id, level_index)
                 for pair in pairs)


def k_candidates(lookup: object, arity: int, page: int, ty: int, tx: int,
                 rows: Sequence[tuple[tuple, object]], first_index: int = 0,
                 ) -> tuple[list[tuple[int, int, np.ndarray, np.ndarray,
                                       np.ndarray]],
                            list[tuple[object, ...]]]:
    from . import calibrate

    y0 = ty * TILE_CELLS
    x0 = tx * TILE_CELLS
    candidates: list[tuple[int, int, np.ndarray, np.ndarray,
                           np.ndarray]] = []
    order_keys: list[tuple[object, ...]] = []
    for offset, (wid, evidence) in enumerate(rows):
        selected = np.flatnonzero(calibrate.payload_cell_mask(
            lookup, evidence.page_cells_yx))
        cells = np.asarray(evidence.page_cells_yx, np.int64)[selected]
        values = np.asarray(evidence.printed_llr, np.float32)[selected]
        inside = ((cells[:, 0] >= y0) & (cells[:, 0] < y0 + TILE_CELLS)
                  & (cells[:, 1] >= x0) & (cells[:, 1] < x0 + TILE_CELLS))
        candidates.append((first_index + offset, page, cells[inside],
                           np.flatnonzero(inside),
                           values[inside].reshape(-1, arity)))
        loss = (np.inf if evidence.heldout_logloss is None
                else float(evidence.heldout_logloss))
        order_keys.append((loss, wid[3], int(evidence.region_index), 0))
    return candidates, order_keys


def color_candidates(geometry: SiteGeometry, arity: int, page: int, ty: int,
                     tx: int, rows: Sequence[tuple[tuple, int, object]],
                     first_index: int = 0,
                     ) -> tuple[list[tuple[int, int, np.ndarray, np.ndarray,
                                           np.ndarray]],
                                list[tuple[object, ...]]]:
    from . import color_region

    y0 = ty * TILE_CELLS
    x0 = tx * TILE_CELLS
    candidates: list[tuple[int, int, np.ndarray, np.ndarray,
                           np.ndarray]] = []
    order_keys: list[tuple[object, ...]] = []
    for offset, (wid, region_index, crow) in enumerate(rows):
        indices = color_region.cargo_row_indices(
            geometry, np.asarray(crow.page_cells_yx, np.int64))
        cells = np.asarray(crow.page_cells_yx, np.int64)[indices]
        values = np.asarray(crow.values, np.float32)[indices]
        inside = ((cells[:, 0] >= y0) & (cells[:, 0] < y0 + TILE_CELLS)
                  & (cells[:, 1] >= x0) & (cells[:, 1] < x0 + TILE_CELLS))
        candidates.append((first_index + offset, page, cells[inside],
                           np.flatnonzero(inside),
                           values[inside].reshape(-1, arity)))
        order_keys.append((float(crow.heldout_logloss), wid[3],
                           int(region_index), 0))
    return candidates, order_keys


def _tile_candidates(store: object, page: int, ty: int, tx: int,
                     capture_id: str, level_index: int,
                     ) -> tuple[list[tuple[int, int, np.ndarray, np.ndarray,
                                           np.ndarray]],
                                list[tuple[object, ...]]]:
    k_wids, color_keys = store.tile_cover(
        (page, ty, tx, capture_id, level_index))
    arity = evidence_arity(store.row)
    candidates, order_keys = k_candidates(
        store.lookup, arity, page, ty, tx,
        tuple((wid, store.evidence(wid)) for wid in k_wids))
    color_rows: list[tuple[tuple, int, object]] = []
    for row_key in color_keys:
        wid = store.window_by_ordinal(capture_id, level_index, row_key[3])
        color_rows.append((wid, int(store.window(wid).region_index),
                           store.color_row(row_key)))
    color_part, color_order = color_candidates(
        store.geometry, arity, page, ty, tx, color_rows, len(candidates))
    return candidates + color_part, order_keys + color_order


def assemble_cut(candidates: Sequence[tuple], order_keys: Sequence[tuple],
                 cells_yx: tuple[int, int], capture_id: str,
                 level_index: int, page: int, ty: int,
                 tx: int) -> TileCut | None:
    owned = freeze_page_owners(list(candidates), cells_yx, list(order_keys))
    if not owned:
        return None
    _page, cells, values, _windows, _rows = owned[0]
    cell_y = cells[:, 0].astype(np.int64)
    cell_x = cells[:, 1].astype(np.int64)
    flat = ((cell_y % TILE_CELLS) * TILE_CELLS
            + (cell_x % TILE_CELLS)).astype(np.uint16)
    return TileCut(capture_id, level_index, page, ty, tx,
                   np.asarray(values, np.float32), flat)


def assemble_tile(store: object, page: int, ty: int, tx: int,
                  capture_id: str, level_index: int) -> TileCut | None:
    candidates, order_keys = _tile_candidates(
        store, page, ty, tx, capture_id, level_index)
    return assemble_cut(candidates, order_keys, store.row.cells_yx,
                        capture_id, level_index, page, ty, tx)


def assemble_union(store: object, page: int, ty: int, tx: int,
                   ppc: Fraction) -> tuple[TileCut, ...]:
    cuts = []
    for capture_id in store.captures():
        level_index = store.level_of_ppc(capture_id, ppc)
        if level_index is None:
            continue
        cut = assemble_tile(store, page, ty, tx, capture_id, level_index)
        if cut is not None:
            cuts.append(cut)
    return tuple(cuts)


def component_signature(components: Sequence[TileCut],
                        ) -> tuple[tuple[str, int], ...]:
    return tuple(sorted((row.capture_id, row.level_index)
                        for row in components))


def attempt_key(page: int, ty: int, tx: int, stream_id: str, stage: str,
                components: Sequence[TileCut],
                ) -> tuple[object, ...]:
    return (page, ty, tx, stream_id, stage, max_iters_for(stage),
            component_signature(components))


def fact_attempt_key(fact: AttemptFact) -> tuple[object, ...]:
    return (fact.page, fact.ty, fact.tx, fact.stream_id, fact.stage,
            max_iters_for(fact.stage), fact.components)


def arms_union(components: Sequence[TileCut]) -> bool:
    return len({row.capture_id for row in components}) >= 2


def arms_retry(fact: AttemptFact, certified: bool) -> bool:
    return (fact.stage in ORDINARY_STAGES
            and fact.outcome == OUTCOME_FAILED
            and not certified)


def _combine(components: Sequence[TileCut], arity: int,
             ) -> tuple[np.ndarray, np.ndarray]:
    dense = np.zeros((N_CELLS, arity), dtype=np.float64)
    observed = np.zeros(N_CELLS, dtype=bool)
    for row in sorted(components, key=lambda item: item.capture_id):
        flat = np.asarray(row.observed_flat, dtype=np.int64)
        dense[flat] += np.asarray(row.values, dtype=np.float64).reshape(
            flat.size, arity)
        observed[flat] = True
    return dense, observed


def _result(page: int, ty: int, tx: int, stream_id: str, stage: str,
            outcome: str, n_informative: int, n_iters: int,
            syndrome_ok: bool | None, crc_ok: bool | None,
            user_bits: np.ndarray | None,
            components: tuple[tuple[str, int], ...] = (),
            ) -> TileAttemptResult:
    source = source_tag(stage)
    certificate = (None if user_bits is None else Certificate(
        page=page, ty=ty, tx=tx, stream_id=stream_id,
        user_bits=np.asarray(user_bits, dtype=np.uint8), source=source))
    fact = AttemptFact(page=page, ty=ty, tx=tx, stream_id=stream_id,
                       stage=stage, outcome=outcome,
                       n_informative=n_informative, n_iters=n_iters,
                       syndrome_ok=syndrome_ok, crc_ok=crc_ok,
                       components=components)
    event = TileOutcome(page=page, ty=ty, tx=tx, stream_id=stream_id,
                        source=source, result=outcome, bp_iters=n_iters)
    return TileAttemptResult(fact, certificate, event)


def _attempt_k(row: FormatRow, geometry: SiteGeometry, page: int, ty: int,
               tx: int, counter: int, dense: np.ndarray, stage: str,
               ) -> TileAttemptResult:
    stream_id = row.streams[0].stream_id
    rate_id, _shorten = row.streams[0].rung_children[0]
    x = dense[:, 0].reshape(TILE_CELLS, TILE_CELLS)
    if not np.isfinite(x).all():
        raise IntegrityError(
            f"tile ({page}, {ty}, {tx}) evidence is not finite — "
            "0.0 is the only erasure spelling")
    site_mask_yx = _site_mask_yx(geometry)
    n_informative = int(np.count_nonzero((x != 0.0) & ~site_mask_yx))
    if n_informative < k_eff_bits(row):
        return _result(page, ty, tx, stream_id, stage, OUTCOME_BELOW_FLOOR,
                       n_informative, 0, None, None, None)
    scramble = _tile_scramble_bits(row, geometry, page, ty, tx, site_mask_yx)
    llr = x * (1.0 - 2.0 * scramble.astype(np.float64))
    llr[site_mask_yx] = 0.0
    ok, user_bits, n_iters, syndrome_ok, crc_ok = tile_codec.decode_tile(
        llr.ravel(), rate_id, geometry.shorten_flat,
        int(geometry.slot_a[counter]), int(geometry.slot_b[counter]),
        max_iters_for(stage), BP_ALPHA)
    if not ok:
        return _result(page, ty, tx, stream_id, stage, OUTCOME_FAILED,
                       n_informative, n_iters, syndrome_ok, crc_ok, None)
    return _result(page, ty, tx, stream_id, stage, OUTCOME_CERTIFIED,
                   n_informative, n_iters, syndrome_ok, crc_ok, user_bits)


def _sequential_payload(row: FormatRow, geometry: SiteGeometry, counter: int,
                        dense: np.ndarray, observed: np.ndarray,
                        ) -> tuple[np.ndarray, np.ndarray]:
    payload_flat = np.asarray(geometry.payload_flat, dtype=np.int64)
    physical = dense[payload_flat]
    physical_observed = observed[payload_flat]
    order = keystream.color_cell_permutation(row.seed, counter,
                                             row.payload_cells)
    sequential = np.empty_like(physical)
    sequential[order] = physical
    sequential_observed = np.empty(row.payload_cells, dtype=bool)
    sequential_observed[order] = physical_observed
    return sequential, sequential_observed


def _color_outcome(outcome: tile_codec.FrameOutcome,
                   ) -> tuple[int, bool, bool | None, np.ndarray | None]:
    _ok, children, _crc_invoked, crc_ok, user_bits, _soft = outcome
    return (sum(n_iters for n_iters, _syndrome_ok in children),
            all(syndrome_ok for _n_iters, syndrome_ok in children),
            crc_ok,
            None if user_bits is None
            else np.asarray(user_bits, dtype=np.uint8))


def _attempt_cmy7(row: FormatRow, page: int, ty: int, tx: int, counter: int,
                  sequential: np.ndarray, observed: np.ndarray,
                  n_informative: int, stage: str) -> TileAttemptResult:
    stream_id = row.streams[0].stream_id
    bank = row.streams[0].rung_children
    transmitted_bits = _bank_transmitted_bits(bank)
    interleave = keystream.cmy7_interleave_permutation(
        row.seed, counter, transmitted_bits)
    complete = observed.reshape(
        -1, tile_codec.CMY7_CELLS_PER_PACK).all(axis=1)
    mapped_support = np.repeat(complete, tile_codec.CMY7_BITS_PER_PACK)
    code_support = np.empty(mapped_support.size, dtype=bool)
    code_support[interleave] = mapped_support
    if not _children_meet_floor(code_support, bank):
        return _result(page, ty, tx, stream_id, stage, OUTCOME_BELOW_FLOOR,
                       n_informative, 0, None, None, None)
    dither = keystream.cmy7_dither_bits(row.seed, counter, transmitted_bits)
    code_llrs = tile_codec.cmy7_demap_payload(
        sequential, observed, bank, interleave, dither)
    if not _children_meet_floor(code_llrs, bank):
        return _result(page, ty, tx, stream_id, stage, OUTCOME_BELOW_FLOOR,
                       n_informative, 0, None, None, None)
    n_iters, syndrome_ok, crc_ok, user_bits = _color_outcome(
        tile_codec.cmy7_iterated_decode(
            code_llrs, sequential, observed, bank, interleave, dither,
            max_iters_for(stage), BP_ALPHA, tile_codec.DEMAP_ITERATIONS))
    outcome = (OUTCOME_FAILED if user_bits is None else OUTCOME_CERTIFIED)
    return _result(page, ty, tx, stream_id, stage, outcome, n_informative,
                   n_iters, syndrome_ok, crc_ok, user_bits)


def _attempt_cmy8(row: FormatRow, page: int, ty: int, tx: int, counter: int,
                  stream_id: str, sequential: np.ndarray,
                  observed: np.ndarray, n_informative: int, stage: str,
                  ) -> TileAttemptResult:
    fact = stream_fact(row, stream_id)
    bank = fact.rung_children
    level_llrs = sequential[:, fact.plane]
    supported = int(np.count_nonzero(observed & (level_llrs != 0.0)))
    if supported < _bank_active_bits(bank):
        return _result(page, ty, tx, stream_id, stage, OUTCOME_BELOW_FLOOR,
                       n_informative, 0, None, None, None)
    dither = keystream.cmy8_dither_bits(
        row.seed, stream_id, counter, _bank_transmitted_bits(bank))
    n_iters, syndrome_ok, crc_ok, user_bits = _color_outcome(
        tile_codec.cmy8_decode_stream(level_llrs, bank, dither,
                                      max_iters_for(stage), BP_ALPHA))
    outcome = (OUTCOME_FAILED if user_bits is None else OUTCOME_CERTIFIED)
    return _result(page, ty, tx, stream_id, stage, outcome, n_informative,
                   n_iters, syndrome_ok, crc_ok, user_bits)


def attempt_tile(row: FormatRow, geometry: SiteGeometry,
                 components: Sequence[TileCut], stream_id: str,
                 stage: str) -> TileAttemptResult:
    page = components[0].page
    ty = components[0].ty
    tx = components[0].tx
    counter = row.tile_counter(page, ty, tx)
    dense, observed = _combine(components, evidence_arity(row))
    if row.family is Family.K:
        result = _attempt_k(row, geometry, page, ty, tx, counter, dense,
                            stage)
    elif row.family is Family.CMY7:
        sequential, sequential_observed = _sequential_payload(
            row, geometry, counter, dense, observed)
        n_informative = int(np.count_nonzero(sequential_observed))
        result = _attempt_cmy7(row, page, ty, tx, counter, sequential,
                               sequential_observed, n_informative, stage)
    else:
        sequential, sequential_observed = _sequential_payload(
            row, geometry, counter, dense, observed)
        n_informative = int(np.count_nonzero(sequential_observed))
        result = _attempt_cmy8(row, page, ty, tx, counter, stream_id,
                               sequential, sequential_observed,
                               n_informative, stage)
    fact = dc_replace(result.fact,
                      components=component_signature(components))
    return TileAttemptResult(fact, result.certificate, result.event)


def printed_cells_for(row: FormatRow, geometry: SiteGeometry, page: int,
                      ty: int, tx: int, user_bits: np.ndarray) -> np.ndarray:
    counter = row.tile_counter(page, ty, tx)
    plane = row.streams[0].plane
    rate_id, _shorten = row.streams[0].rung_children[0]
    cells = tile_codec.encode_tile(
        np.asarray(user_bits, dtype=np.uint8).ravel(), rate_id,
        geometry.shorten_flat, int(geometry.slot_a[counter]),
        int(geometry.slot_b[counter]))
    tile = cells.reshape(TILE_CELLS, TILE_CELLS).copy()
    word_y = geometry.word_cells_yx[:, 0]
    word_x = geometry.word_cells_yx[:, 1]
    word = pilots.word_values(row.seed, counter, plane)[0]
    tile[word_y, word_x] = word
    known_y = word_y
    known_x = word_x
    known_values = word
    if geometry.extra_cells_yx.size:
        filler_y = geometry.extra_cells_yx[:, 0]
        filler_x = geometry.extra_cells_yx[:, 1]
        filler = keystream.bits(
            row.seed, keystream.DOMAIN_FILLER_VALUES, plane, page,
            ty * TILE_CELLS + filler_y, tx * TILE_CELLS + filler_x)
        tile[filler_y, filler_x] = filler
        known_y = np.concatenate((word_y, filler_y))
        known_x = np.concatenate((word_x, filler_x))
        known_values = np.concatenate((word, filler))
    field = tile ^ _tile_scramble_bits(row, geometry, page, ty, tx,
                                       _site_mask_yx(geometry))
    if not np.array_equal(field[known_y, known_x], known_values):
        raise IntegrityError(
            f"certified re-encode at tile ({page}, {ty}, {tx}) disagrees "
            "with the format field at a format-known site — wrong address "
            "or forked keystream")
    return field


def merge_certificate(certs: dict[TileKey, Certificate],
                      certificate: Certificate) -> bool:
    key: TileKey = (certificate.page, certificate.ty, certificate.tx,
                    certificate.stream_id)
    standing = certs.get(key)
    if standing is None:
        certs[key] = certificate
        return True
    if not np.array_equal(standing.user_bits, certificate.user_bits):
        raise IntegrityError(
            f"conflicting certificates at {key}: {standing.source} and "
            f"{certificate.source} certify different user bits")
    return False


def close_input(certs: dict[TileKey, Certificate],
                ) -> tuple[Certificate, ...]:
    return tuple(certs[key] for key in sorted(certs))


def unresolved_streams(row: FormatRow, certs: dict[TileKey, Certificate],
                       page: int, ty: int, tx: int) -> tuple[str, ...]:
    return tuple(fact.stream_id for fact in row.streams
                 if (page, ty, tx, fact.stream_id) not in certs)


def tile_done(row: FormatRow, certs: dict[TileKey, Certificate], page: int,
              ty: int, tx: int) -> bool:
    return not unresolved_streams(row, certs, page, ty, tx)


def done_tile_grid(row: FormatRow, certs: dict[TileKey, Certificate],
                   page: int) -> np.ndarray:
    tiles_y, tiles_x = row.tiles_yx
    grid = np.zeros((tiles_y, tiles_x), dtype=bool)
    seen: dict[tuple[int, int], set[str]] = {}
    for cert_page, ty, tx, stream_id in certs:
        if cert_page != page:
            continue
        seen.setdefault((ty, tx), set()).add(stream_id)
    wanted = {fact.stream_id for fact in row.streams}
    for (ty, tx), names in seen.items():
        if wanted <= names and 0 <= ty < tiles_y and 0 <= tx < tiles_x:
            grid[ty, tx] = True
    return grid


def project_done(poses: Iterable[DonePose], grids: dict[int, np.ndarray],
                 origin_yx: tuple[int, int], pitch_px: float,
                 shape_cells: tuple[int, int],
                 support: np.ndarray) -> np.ndarray:
    done = np.zeros(shape_cells, dtype=bool)
    for page, extent_cells, native_affine in poses:
        grid = grids.get(page)
        if grid is None or not grid.any():
            continue
        cy0, cx0, cy1, cx1 = extent_cells
        shape = (cy1 - cy0, cx1 - cx0)
        centres_y = origin_yx[0] + pitch_px * (
            np.arange(cy0, cy1, dtype=np.float64) + 0.5)
        centres_x = origin_yx[1] + pitch_px * (
            np.arange(cx0, cx1, dtype=np.float64) + 0.5)
        cell_y, cell_x = apply_affine(
            invert_affine(native_affine),
            np.broadcast_to(centres_y[:, None], shape),
            np.broadcast_to(centres_x[None, :], shape))
        ty, tx = tile_of_cell(np.floor(cell_y).astype(np.int64),
                              np.floor(cell_x).astype(np.int64))
        inside = ((ty >= 0) & (ty < grid.shape[0])
                  & (tx >= 0) & (tx < grid.shape[1]))
        marked = np.zeros(inside.shape, dtype=bool)
        marked[inside] = grid[ty[inside], tx[inside]]
        done[cy0:cy1, cx0:cx1] |= marked & support[cy0:cy1, cx0:cx1]
    return done


def done_covers(done: np.ndarray, extent_cells: tuple[int, int, int, int],
                support: np.ndarray) -> bool:
    cy0, cx0, cy1, cx1 = extent_cells
    window_support = support[cy0:cy1, cx0:cx1]
    if not window_support.any():
        return False
    return bool(np.all(done[cy0:cy1, cx0:cx1][window_support]))


def _attempt_many(row: FormatRow, geometry: SiteGeometry,
                  components: tuple[TileCut, ...],
                  stream_ids: tuple[str, ...], stage: str) -> JobResult:
    started = time.thread_time()
    facts: list[object] = []
    events: list[object] = []
    for stream_id in stream_ids:
        result = attempt_tile(row, geometry, components, stream_id, stage)
        facts.append(result.fact)
        if result.certificate is not None:
            facts.append(result.certificate)
        events.append(result.event)
    return JobResult(tuple(facts), tuple(events),
                     time.thread_time() - started)


def _uncertified_streams(store: object, page: int, ty: int,
                         tx: int) -> tuple[str, ...]:
    return tuple(
        stream.stream_id for stream in store.row.streams
        if not store.has_certificate((page, ty, tx, stream.stream_id)))


def prepare_scan(store: object, subject: Subject,
                  stage: str) -> Job | None:
    page, ty, tx, capture_id, level_index = subject
    cut = assemble_tile(store, page, ty, tx, capture_id, level_index)
    if cut is None:
        return None
    components = (cut,)
    pending = _uncertified_streams(store, page, ty, tx)
    if not pending:
        return None
    row = store.row
    site_geometry = store.geometry

    def job() -> JobResult:
        return _attempt_many(row, site_geometry, components, pending,
                             STAGE_SCAN)

    return job


def prepare_union(store: object, subject: Subject,
                  stage: str) -> Job | None:
    page, ty, tx, ppc = subject
    components = assemble_union(store, page, ty, tx, ppc)
    if not arms_union(components):
        return None
    pending = _uncertified_streams(store, page, ty, tx)
    if not pending:
        return None
    row = store.row
    site_geometry = store.geometry

    def job() -> JobResult:
        return _attempt_many(row, site_geometry, components, pending,
                             STAGE_UNION)

    return job


def prepare_retry(store: object, subject: Subject,
                  stage: str) -> Job | None:
    origin, page, ty, tx, stream_id, lane, capture_id = subject
    if origin == STAGE_SCAN:
        cut = assemble_tile(store, page, ty, tx, capture_id, lane)
        components = () if cut is None else (cut,)
    else:
        components = assemble_union(store, page, ty, tx, lane)
        if not arms_union(components):
            return None
    if not components:
        return None
    if store.has_certificate((page, ty, tx, stream_id)):
        return None
    baseline = attempt_key(page, ty, tx, stream_id, origin, components)
    if store.attempt_outcome(baseline) != OUTCOME_FAILED:
        return None
    row = store.row
    site_geometry = store.geometry

    def job() -> JobResult:
        return _attempt_many(row, site_geometry, components, (stream_id,),
                             STAGE_RETRY150)

    return job


PLUGIN_SCAN: str = "tiles.scan"
PLUGIN_UNION: str = "tiles.union"
PLUGIN_RETRY: str = "tiles.retry"


def _static_stage(name: str) -> Callable[[object, Subject], str | None]:
    def stage(store: object, subject: Subject) -> str | None:
        return name

    return stage


def _scan_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    if isinstance(fact, WindowEvidence):
        return store.window_cover_tiles(fact.window_id)
    return store.color_row_cover_tiles(
        (fact.capture_id, fact.level_index, fact.page, fact.patch_ordinal))


def _scan_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    k_wids, color_keys = store.tile_cover(subject)
    keys: list[FactKey] = []
    for wid in k_wids:
        keys.append((KEY_EVIDENCE_FIT, wid))
        keys.append((KEY_EVIDENCE_READ, wid))
    for row_key in color_keys:
        keys.append((KEY_COLOR_ROW,) + row_key)
    return tuple(keys)


def _scan_eligible(store: object, subject: Subject) -> bool:
    return bool(_uncertified_streams(store, subject[0], subject[1],
                                     subject[2]))


def _scan_retire(store: object, subject: Subject) -> bool:
    return not _scan_eligible(store, subject)


def _scan_cost(store: object, subject: Subject, stage: str,
               attempts: int, last_cost: int) -> int:
    return PAYLOAD_COST + RUNG_COST * subject[4]


def _union_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    subjects: list[Subject] = []
    for page, ty, tx, capture_id, level_index in _scan_subjects(store,
                                                                fact):
        ppc = store.level(capture_id, level_index).ppc
        lanes = store.cover_lanes(page, ty, tx, ppc)
        if len({lane_capture for lane_capture, _index in lanes}) >= 2:
            subjects.append((page, ty, tx, ppc))
    return tuple(dict.fromkeys(subjects))


def _union_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    page, ty, tx, ppc = subject
    keys: list[FactKey] = []
    for capture_id, level_index in store.cover_lanes(page, ty, tx, ppc):
        keys.extend(_scan_reads(store,
                                (page, ty, tx, capture_id, level_index)))
    return tuple(keys)


def _union_cost(store: object, subject: Subject, stage: str,
                attempts: int, last_cost: int) -> int:
    return PAYLOAD_COST + RUNG_COST * store.union_rung_ordinal(subject[3])


def _retry_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    if not fact.components:
        return ()
    certified = store.has_certificate(
        (fact.page, fact.ty, fact.tx, fact.stream_id))
    if not arms_retry(fact, certified):
        return ()
    if fact.stage == STAGE_SCAN:
        capture_id, lane = fact.components[0]
    else:
        capture_id = None
        lane = store.level(*fact.components[0]).ppc
    return ((fact.stage, fact.page, fact.ty, fact.tx, fact.stream_id,
             lane, capture_id),)


def _retry_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    origin, page, ty, tx, _stream_id, lane, capture_id = subject
    if origin == STAGE_SCAN:
        return _scan_reads(store, (page, ty, tx, capture_id, lane))
    return _union_reads(store, (page, ty, tx, lane))


def _retry_eligible(store: object, subject: Subject) -> bool:
    page, ty, tx, stream_id = subject[1], subject[2], subject[3], subject[4]
    return not store.has_certificate((page, ty, tx, stream_id))


def _retry_retire(store: object, subject: Subject) -> bool:
    return not _retry_eligible(store, subject)


def _retry_cost(store: object, subject: Subject, stage: str,
                attempts: int, last_cost: int) -> int:
    if subject[0] == STAGE_SCAN:
        return PAYLOAD_COST + RUNG_COST * subject[5]
    return PAYLOAD_COST + RUNG_COST * store.union_rung_ordinal(subject[5])


SCAN_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN_SCAN,
    subject_kind="tile",
    born_by=(WindowEvidence, ColorEvidenceRow),
    subjects_of=_scan_subjects,
    reads=_scan_reads,
    eligible=_scan_eligible,
    stage=_static_stage(STAGE_PAYLOAD),
    cost=_scan_cost,
    retire=_scan_retire,
    prepare=prepare_scan,
    produces=(AttemptFact, Certificate),
    prices=PRICES,
)

UNION_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN_UNION,
    subject_kind="tile",
    born_by=(WindowEvidence, ColorEvidenceRow),
    subjects_of=_union_subjects,
    reads=_union_reads,
    eligible=_scan_eligible,
    stage=_static_stage(STAGE_PAYLOAD),
    cost=_union_cost,
    retire=_scan_retire,
    prepare=prepare_union,
    produces=(AttemptFact, Certificate),
    prices=PRICES,
)

RETRY_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN_RETRY,
    subject_kind="tile",
    born_by=(AttemptFact,),
    subjects_of=_retry_subjects,
    reads=_retry_reads,
    eligible=_retry_eligible,
    stage=_static_stage(STAGE_PAYLOAD),
    cost=_retry_cost,
    retire=_retry_retire,
    prepare=prepare_retry,
    produces=(AttemptFact, Certificate),
    prices=PRICES,
)

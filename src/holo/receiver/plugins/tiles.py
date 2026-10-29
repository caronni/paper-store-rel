from __future__ import annotations

import time
from dataclasses import dataclass
from dataclasses import replace as dc_replace
from fractions import Fraction
from typing import Iterable, Sequence

import numpy as np

from ..data import (
    AttemptFact,
    Certificate,
    IntegrityError,
    JobResult,
    TileOutcome,
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
from .color_sites import cargo_row_indices

#: The two BP budgets, defined here and nowhere else
#: (00-contract.md:373-374).  150 is what the retry tier buys: it
#: converts real marginal tiles on the e029/e032 corpus, and one retry
#: per evidence set suffices because BP is deterministic (02-ldpc.md:303).
BASELINE_BP_MAX_ITERS: int = 60
RETRY_BP_MAX_ITERS: int = 150
#: Normalized min-sum scaling, part of the DECODER IDENTITY: 0.8 with
#: 60/150 are the values every measured close ran under, so moving one
#: forks the receiver from its own record (02-ldpc.md:398-400).
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
# the conditioned label stream (tiles_sched's `tiles.cond`, CMY-DESIGN
# R5): one cmy stream decoded given its certified sibling's label bits.
# It runs once per generation with no retry behind it, so its one
# attempt takes the budget the retry tier buys.
STAGE_COND150: str = "cond150"
ORDINARY_STAGES: tuple[str, str] = (STAGE_SCAN, STAGE_UNION)
HEAVY_STAGES: frozenset[str] = frozenset(
    {STAGE_RETRY150, STAGE_LOCAL150, STAGE_UPLIFT_A3, STAGE_UPLIFT_A4B,
     STAGE_PLANEK150, STAGE_SWIM150, STAGE_COND150})

OUTCOME_BELOW_FLOOR: str = "below_attempt_floor"
OUTCOME_FAILED: str = "attempted_failed"
OUTCOME_CERTIFIED: str = "certified"

PLUGIN: str = "tiles"
N_CELLS: int = tile_codec.N_CELLS
#: Evidence columns per cell: K one calibrated LLR, CMY7 six W-relative
#: state scores, CMY8 three per-plane presence LLRs in C,M,Y order --
#: the same order StreamFact.plane indexes into
#: (12-tiles-payload.md:20-25, 54-58) -- and CMY three W-relative state
#: scores in C,M,Y order, which `stream_llrs` demaps per label stream.
ARITY_BY_FAMILY: dict[Family, int] = {
    Family.K: 1, Family.CMY7: 6, Family.CMY8: 3, Family.CMY: 3}

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


#: Unknown info bits = k_bits minus the known-zero site tail; below it
#: the tile is refused before any decoder runs (02-ldpc.md:306-307).  A
#: COUNTING floor, deliberately conservative: the framed CRC leaves
#: k_eff-32 real degrees of freedom (docs/RECEIVE-DESIGN-EVIDENCE.md:126).
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
    cells = np.asarray(page_cells_yx, np.int64)
    return cells[cargo_row_indices(geometry, cells)]


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
        # An accepted window always carries its loss, so the inf branch is
        # unreachable: only accepted evidence ever enters a tile cover.  Keep
        # it that way -- holo2 measured 0 of 6 re-read windows ranked, and an
        # inf window loses every contested cell it touches.
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
    y0 = ty * TILE_CELLS
    x0 = tx * TILE_CELLS
    candidates: list[tuple[int, int, np.ndarray, np.ndarray,
                           np.ndarray]] = []
    order_keys: list[tuple[object, ...]] = []
    for offset, (wid, region_index, crow) in enumerate(rows):
        indices = cargo_row_indices(
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


#: THE LANE AN ATTEMPT READ, and the one rule that works for the wake
#: key.  A single-component attempt names its lane exactly; a summed one
#: names the FOOTING its components share, because `assemble_union`
#: produces at most one cut per capture at one declared ppc and
#: `arms_union` demands two distinct captures, so `len == 1` is
#: single-lane exactly.
#:
#: Keying on the stage alone would collapse every scan-origin verdict at
#: one footing onto one key, and two lanes would flip-flop each other's
#: verdict; keying on the whole component tuple would make the key
#: unreadable from a subscriber's SUBJECT, because a residue row does
#: not assemble its components until `prepare`.  Several component SETS
#: at one footing therefore share a key -- over-declaring, which costs
#: extra wakes and never wrongness, while the fold's adopt test keeps
#: the precise component-keyed ledger.
def attempt_lane(store: object,
                 fact: AttemptFact) -> tuple[str, int] | Fraction | None:
    if not fact.components:
        return None
    if len(fact.components) == 1:
        return fact.components[0]
    return store.level(*fact.components[0]).ppc


#: THE FOOTING AN ATTEMPT READ: the declared ppc its components share,
#: whether it read one lane or summed several.  A lane's footing is a
#: property of its capture's level and never moves, so a failure keyed
#: here outlives the lane's place in the cover (store
#: `attempt_ever_failed_at_footing`).
def attempt_footing(store: object, fact: AttemptFact) -> Fraction | None:
    if not fact.components:
        return None
    return store.level(*fact.components[0]).ppc


#: `(page, ty, tx, stream_id, stage, lane)` -- the KEY_ATTEMPT key's
#: tail, which is what a subscriber can spell from its own subject.
def attempt_wake_key(store: object,
                     fact: AttemptFact) -> tuple[object, ...]:
    return (fact.page, fact.ty, fact.tx, fact.stream_id, fact.stage,
            attempt_lane(store, fact))


#: Union sums >=2 DISTINCT physical captures at one declared footing.
#: Equal-weight combining LOSES to best-single until the ctx detector
#: de-correlates print-frozen errors, and a capture summed with its own
#: decimation is one capture twice (12-tiles-payload.md:296-298).
def arms_union(components: Sequence[TileCut]) -> bool:
    return len({row.capture_id for row in components}) >= 2


#: A retry needs a FAILED BASELINE -- a decoder ran on this exact
#: evidence and lost.  Below-floor is not that (no decoder ran), and
#: deriving retries from a tile-level "attempted" armed BP-150 on
#: footings whose baseline never ran (12-tiles-payload.md:411-413).
def arms_retry(fact: AttemptFact, certified: bool) -> bool:
    return (fact.stage in ORDINARY_STAGES
            and fact.outcome == OUTCOME_FAILED
            and not certified)


#: Independent captures SUM and nothing clamps afterwards: each
#: capture's LLR is already bounded by its own PAVA label count
#: (018.7).  A fixed post-sum clamp changes reliability ratios and was
#: never qualified (12-tiles-payload.md:286-288).
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
    # Accepting an infinity here once turned an entry the k_eff floor had
    # excluded into a maximum-strength decoder input; 0.0 is the erasure
    # and the only spelling of one (12-tiles-payload.md:289-290, 395-396).
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


#: The structural pack gate runs BEFORE the demapper so a starved child
#: never pays for it, and the same per-child floor is re-checked on the
#: demapped LLRs.  code_support[interleave] = ... is a SCATTER;
#: gathering instead silently misgates children (12-tiles-payload.md:409).
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


#: One stream's level LLRs from the sequential evidence: a toner
#: stream's column (cmy8's per-plane presence LLR), or a label stream's
#: bit demapped from the cell's three W-relative state scores (cmy),
#: conditioned on the sibling stream's label bits where they are known.
#: Only a label stream conditions at the attempt: cmy8's A4b does it at
#: evidence time.
def stream_llrs(row: FormatRow, fact: StreamFact, sequential: np.ndarray,
                sibling: np.ndarray | None = None) -> np.ndarray:
    if fact.label_index is None:
        if sibling is not None:
            raise ValueError(
                f"stream {fact.stream_id!r} is a toner stream: it has no "
                "label sibling to condition on")
        return sequential[:, fact.plane]
    if row.family is not Family.CMY:
        raise KeyError(row.family)
    return tile_codec.cmy_soft_demap(sequential, fact.label_index, sibling)


def _attempt_stream(row: FormatRow, page: int, ty: int, tx: int,
                    counter: int, stream_id: str, sequential: np.ndarray,
                    observed: np.ndarray, n_informative: int, stage: str,
                    sibling: np.ndarray | None = None,
                    ) -> TileAttemptResult:
    fact = stream_fact(row, stream_id)
    bank = fact.rung_children
    level_llrs = stream_llrs(row, fact, sequential, sibling)
    supported = int(np.count_nonzero(observed & (level_llrs != 0.0)))
    if supported < _bank_active_bits(bank):
        return _result(page, ty, tx, stream_id, stage, OUTCOME_BELOW_FLOOR,
                       n_informative, 0, None, None, None)
    dither = keystream.cmy8_dither_bits(
        row.seed, fact.dither_aux, counter, _bank_transmitted_bits(bank))
    n_iters, syndrome_ok, crc_ok, user_bits = _color_outcome(
        tile_codec.cmy8_decode_stream(level_llrs, bank, dither,
                                      max_iters_for(stage), BP_ALPHA))
    outcome = (OUTCOME_FAILED if user_bits is None else OUTCOME_CERTIFIED)
    return _result(page, ty, tx, stream_id, stage, outcome, n_informative,
                   n_iters, syndrome_ok, crc_ok, user_bits)


def attempt_tile(row: FormatRow, geometry: SiteGeometry,
                 components: Sequence[TileCut], stream_id: str,
                 stage: str, generation: int = 0,
                 sibling: np.ndarray | None = None) -> TileAttemptResult:
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
    elif row.family in (Family.CMY8, Family.CMY):
        sequential, sequential_observed = _sequential_payload(
            row, geometry, counter, dense, observed)
        n_informative = int(np.count_nonzero(sequential_observed))
        result = _attempt_stream(row, page, ty, tx, counter, stream_id,
                                 sequential, sequential_observed,
                                 n_informative, stage, sibling)
    else:
        raise KeyError(row.family)
    fact = dc_replace(result.fact,
                      components=component_signature(components),
                      generation=int(generation))
    return TileAttemptResult(fact, result.certificate, result.event)


#: The known-site agreement check stays at MINT time (contract ruling
#: 12-3): one array compare against the format field, and it catches a
#: wrong address or a forked keystream before these cells become
#: refine's pose targets (00-contract.md:294-295).
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


#: Both sides carry a CRC-32 certificate, so differing bits are not a
#: noise event (2^-32 class): mixed sheets or an upstream fault.  Fatal
#: by doctrine, never voted, never broken by recency; an identical
#: duplicate is corroboration (12-tiles-payload.md:160-163).
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


#: One pose per window, the LATEST -- never the union with its parent.
#: MEASURED: unioning parent and revision added +860 done cells on e029
#: and +588 on xerox, geometry a revision bought without sampling a
#: pixel (12-tiles-payload.md:214-216).
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


#: An all-unsupported extent is DEAD, not done: answering True would
#: retire a window on the strength of cells nothing ever printed
#: (12-tiles-payload.md:213-214).
def done_covers(done: np.ndarray, extent_cells: tuple[int, int, int, int],
                support: np.ndarray) -> bool:
    cy0, cx0, cy1, cx1 = extent_cells
    window_support = support[cy0:cy1, cx0:cx1]
    if not window_support.any():
        return False
    return bool(np.all(done[cy0:cy1, cx0:cx1][window_support]))


#: `sibling` is the certified sibling's label bits in the codec's
#: sequential order, handed to every listed stream: `tiles.cond` lists
#: the one stream it conditions, every other stage none.
def attempt_many(row: FormatRow, geometry: SiteGeometry,
                 components: tuple[TileCut, ...],
                 stream_ids: tuple[str, ...], stage: str,
                 generation: int = 0,
                 sibling: np.ndarray | None = None) -> JobResult:
    started = time.thread_time()
    facts: list[object] = []
    events: list[object] = []
    for stream_id in stream_ids:
        result = attempt_tile(row, geometry, components, stream_id, stage,
                              generation, sibling)
        facts.append(result.fact)
        if result.certificate is not None:
            facts.append(result.certificate)
        events.append(result.event)
    return JobResult(tuple(facts), tuple(events),
                     time.thread_time() - started)

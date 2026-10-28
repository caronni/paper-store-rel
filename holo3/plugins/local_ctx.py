"""tiles.local — re-read one failed tile under a locally fitted head.

Both arms re-fit, over the windows that cover ONE failed tile, whatever
the standing receiver fits region-wide — then re-attempt that tile alone
under the result.  The local fit is transient in both: built inside the
job, used for one decoder input, discarded.  Nothing this row does can
change a standing evidence row, a standing region context cell or any
other tile's read.

K arm.  The standing context detector (`calibrate.CTX_DESCRIPTOR`) fits
ONE nine-bin neighbour-count correction per region.  This row fits that
same correction over the covering windows alone, on labels those windows
can prove.

Colour arm.  Colour has no separate context row: `color_region` fits the
WHOLE head per lane and page in one job — QDA class model, the CMY8
detector calibration or the CMY7 head, the registration residuals, the
feature divisor, and the state x plane x bin context matrix
(`color_region_ctx.fit_region_context`) — and applies it to every window
on the page.  So for colour the region-wide object is the entire head,
and localising it means running `color_region.region_job` over the
covering windows alone.  That is exactly what a crop does, and it is why
this arm is a bigger lever than K's: the crop-parity batteries found
tiles that fail full-sheet under both receiver generations and certify
from a crop.

Why the row exists at all: a crop is an accidental local head — its
survey, its placement and its fit all see only the crop.  This row makes
that deliberate, one tile at a time, without touching the page.

How the fire is spent.  The covering lanes are re-fitted once — that is
the expensive half — and then read TWICE over: first as a union of all
of them, and, only if that mints nothing, once per lane on its own,
stopping at the first certificate.  `attempt_sets` carries the measured
reason for both halves; in short, summing lanes wins an observation
floor and loses a vote, so the row takes both.  Single-lane tiles are
untouched: there the union is the lane.

What the K arm does NOT do, and why: it does not re-fit the per-window
score-to-probability head on a local population.  That arm is measured
(docs/TOOLBOX-INVENTORY §6.13, `measure/calibration/e9_k.py`, e029's
complete 21-tile residue): zero certificates from every local arm at
both lanes, with the arms ordered page-global > 2-window halo >
1-window halo > window-only.  What paid there was DENSE CERTIFIED
LABELS, not locality — so that is what this row carries into the one
fit the standing receiver still makes region-wide.  Colour is the
opposite case and the record says so: the per-window photometric map
(§6.5, A3) measured +46 certificates on hp c3-cmy8 and +6/+7 as a
supplemental lane, because colour's class model IS region-wide and a
window's own photometry is not the region's.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from typing import Sequence

import numpy as np

from ..data import (
    AttemptFact,
    Certificate,
    ColorEvidenceRow,
    JobResult,
    LaneKey,
    PlaneRaster,
    RegionCtx,
    WindowEvidence,
    WindowId,
)
from ..descriptor import (
    FactKey,
    Job,
    KEY_COLOR_ROW,
    KEY_EVIDENCE_FIT,
    KEY_EVIDENCE_READ,
    KEY_TILE,
    PluginDescriptor,
    Subject,
)
from ..format.identity import Family, FormatRow, SiteGeometry
from ..lib.geometry import TILE_CELLS, WINDOW_CELLS, site_parity
from ..lib.pava import N_CONTEXT_BINS, calibration_llr
from . import calibrate, color_region, refine, tiles

PLUGIN: str = "tiles.local"
STAGE_LOCAL: str = "local"

# late residue work: the row does a calibrate-class context fit (15) AND
# a heavy payload attempt (20) on top of a pose the refinement rows may
# still move under it (200), so it queues behind every one of them.
LOCAL_COST: int = 220
RUNG_COST: int = 2
PRICES: tuple[tuple[str, int], ...] = ((STAGE_LOCAL, LOCAL_COST),)

# A failed ordinary or retried attempt is what gives this row a subject.
# Its own facts never arm it again — one local fit per (tile, footing),
# re-fired only when the evidence or a neighbouring certificate moves.
ARMING_STAGES: tuple[str, ...] = (
    tiles.STAGE_SCAN, tiles.STAGE_UNION, tiles.STAGE_RETRY150)

# The neighbourhood is not a chosen radius: it is exactly the set of
# tiles the windows covering the target tile also cover, read from the
# store.  This bound is what the window grid makes possible — a
# WINDOW_CELLS-wide window straddles at most this many tile boundaries —
# and exists so a test can pin the derivation instead of a constant.
MAX_NEIGHBOUR_TILE_RADIUS: int = -(-(WINDOW_CELLS - 1) // TILE_CELLS)

REASON_NO_LABELS: str = "no_local_labels"

# subject: (page, ty, tx, stream_id, ppc) -- one local read per tile per
# printed footing, over every lane that covers the tile at that footing
TileAddress = tuple[int, int]


@dataclass(frozen=True)
class LanePlan:
    """Everything one lane's local K fit needs, read from the store once."""

    lane: LaneKey
    rows: tuple[tuple[WindowId, WindowEvidence], ...]


@dataclass(frozen=True)
class ColorLanePlan:
    """Everything one lane's local COLOUR head needs, read once.

    `windows` are the covering windows in `color_region`'s own geometry;
    `ordinals` names them so the head's output rows can be matched back
    to the window ids the tile cut orders by.
    """

    lane: LaneKey
    windows: tuple[object, ...]
    ordinals: tuple[tuple[int, WindowId, int], ...]
    planes: tuple[PlaneRaster, PlaneRaster, PlaneRaster]


@dataclass(frozen=True)
class LocalFit:
    offsets: np.ndarray
    adopted: bool
    reason: str
    n_search_sites: int
    validation_logloss: float | None


def _zero_offsets() -> np.ndarray:
    return np.zeros(N_CONTEXT_BINS, np.float64)


def covering_windows(store: object, page: int, ty: int, tx: int,
                     lane: LaneKey) -> tuple[WindowId, ...]:
    k_wids, _color_keys = store.tile_cover(
        (page, ty, tx, lane[0], lane[1]))
    return k_wids


def covering_color_rows(store: object, page: int, ty: int, tx: int,
                        lane: LaneKey) -> tuple[tuple, ...]:
    _k_wids, color_keys = store.tile_cover(
        (page, ty, tx, lane[0], lane[1]))
    return color_keys


def neighbourhood_tiles(store: object, page: int, ty: int, tx: int,
                        ppc: Fraction) -> tuple[TileAddress, ...]:
    """The tiles the windows covering (ty, tx) cover — the local frame.

    Both covers answer the same question — what else does a window that
    sees this tile see — so K windows contribute their evidence reach
    and colour rows their own cover keys.
    """
    found: set[TileAddress] = set()
    for lane in store.cover_lanes(page, ty, tx, ppc):
        for wid in covering_windows(store, page, ty, tx, lane):
            reach = store.evidence_reach(wid)
            if reach is not None:
                found.update(reach)
        for row_key in covering_color_rows(store, page, ty, tx, lane):
            for cover in store.color_row_cover_tiles(row_key):
                found.add((cover[1], cover[2]))
    return tuple(sorted(found))


def certified_neighbours(store: object, page: int,
                         reach: Sequence[TileAddress],
                         target: TileAddress) -> tuple[TileAddress, ...]:
    """Neighbourhood tiles carrying a certificate — the extra labels.

    One certified stream is enough: K has only one, and a colour tile
    with two of three streams certified still projects those two planes
    as known cells (`color_region.certified_projection`).
    """
    streams = store.row.streams
    return tuple(
        (ty, tx) for ty, tx in reach
        if (ty, tx) != target
        and any(store.has_certificate((page, ty, tx, stream.stream_id))
                for stream in streams))


def label_values(page: int, evidence: WindowEvidence,
                 printed: dict[tuple[int, int, int], np.ndarray],
                 ) -> np.ndarray:
    """Per-cell labels for one window: format truth plus certified cargo.

    Provenance is the refinement row's, exactly: `reference_values` are
    the format's own word and filler bits, and every cargo label comes
    from `refine.certified_fields`, i.e. from a certificate re-encoded
    through the printed format.  No provisional decision is ever a
    label.  Cells with no proof carry -1 and take no part in the fit.
    """
    cells = np.asarray(evidence.page_cells_yx, np.int64)
    labels = refine.collect_labels(page, cells, evidence.reference_values,
                                   printed)
    values = np.full(cells.shape[0], -1, np.int8)
    values[labels.rows] = np.asarray(labels.values, np.int8)
    return values


def _fit_parts(evidence: WindowEvidence, values: np.ndarray,
               site_ids: np.ndarray,
               ) -> tuple[tuple[np.ndarray, ...], tuple[np.ndarray, ...]]:
    marginal = np.asarray(
        calibration_llr(evidence.scores, evidence.knots, evidence.probs),
        np.float64)
    counts, valid = calibrate.context_neighbour_counts(
        evidence.page_cells_yx, marginal > 0.0)
    cells = np.asarray(evidence.page_cells_yx, np.int64)
    known = np.asarray(values, np.int8) >= 0
    heldout = site_parity(cells[:, 0], cells[:, 1]).astype(bool)
    search = known & ~heldout & valid
    validation = known & heldout & valid
    return ((marginal[search], counts[search],
             np.asarray(values, np.int8)[search].astype(bool),
             site_ids[search]),
            (marginal[validation], counts[validation],
             np.asarray(values, np.int8)[validation].astype(bool),
             site_ids[validation]))


def _pool(parts: Sequence[tuple[np.ndarray, ...]],
          ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    live = [part for part in parts if part[0].size]
    if not live:
        return (np.zeros(0, np.float64), np.zeros(0, np.int8),
                np.zeros(0, bool), np.zeros(0, np.int64))
    return (np.concatenate([part[0] for part in live]),
            np.concatenate([part[1] for part in live]),
            np.concatenate([part[2] for part in live]),
            np.concatenate([part[3] for part in live]))


def fit_local_context(rows: Sequence[WindowEvidence],
                      values: Sequence[np.ndarray]) -> LocalFit:
    """The standing context fit, over these windows and these labels."""
    site_ids = calibrate.physical_cell_ids(tuple(rows))
    search_parts = []
    validation_parts = []
    for evidence, row_values, ids in zip(rows, values, site_ids,
                                         strict=True):
        search, validation = _fit_parts(evidence, row_values, ids)
        search_parts.append(search)
        validation_parts.append(validation)
    search = _pool(search_parts)
    validation = _pool(validation_parts)
    if not search[0].size:
        return LocalFit(_zero_offsets(), False, REASON_NO_LABELS, 0, None)
    offsets, adopted, reason, _baseline, candidate = (
        calibrate.context_decision(search, validation))
    return LocalFit(offsets, adopted, reason, int(search[0].size),
                    candidate)


def local_context_row(evidence: WindowEvidence,
                      fit: LocalFit) -> WindowEvidence:
    """One window read under the local offsets — never folded anywhere."""
    ctx = RegionCtx(evidence.capture_id, evidence.level_index,
                    evidence.region_index, fit.offsets, True,
                    f"local/{fit.reason}", fit.validation_logloss)
    return calibrate.apply_standing_context(evidence, ctx)


def local_cut(plan: LanePlan, fit: LocalFit, lookup: object, arity: int,
              cells_yx: tuple[int, int], page: int, ty: int,
              tx: int) -> tiles.TileCut | None:
    rows = tuple((wid, local_context_row(evidence, fit))
                 for wid, evidence in plan.rows)
    candidates, order_keys = tiles.k_candidates(
        lookup, arity, page, ty, tx, rows)
    return tiles.assemble_cut(candidates, order_keys, cells_yx,
                              plan.lane[0], plan.lane[1], page, ty, tx)


def _lane_plans(store: object, page: int, ty: int, tx: int,
                ppc: Fraction) -> tuple[LanePlan, ...]:
    plans: list[LanePlan] = []
    for lane in store.cover_lanes(page, ty, tx, ppc):
        rows = tuple(
            (wid, evidence)
            for wid in covering_windows(store, page, ty, tx, lane)
            if (evidence := store.evidence(wid)) is not None
            and evidence.accepted)
        if rows:
            plans.append(LanePlan(lane, rows))
    return tuple(plans)


def _color_lane_plans(store: object, page: int, ty: int, tx: int,
                      ppc: Fraction) -> tuple[ColorLanePlan, ...]:
    plans: list[ColorLanePlan] = []
    for lane in store.cover_lanes(page, ty, tx, ppc):
        ordinals: list[tuple[int, WindowId, int]] = []
        windows: list[object] = []
        for row_key in covering_color_rows(store, page, ty, tx, lane):
            patch_ordinal = int(row_key[3])
            wid = store.window_by_ordinal(lane[0], lane[1], patch_ordinal)
            window = store.window(wid)
            if store.placement(wid) is None or window is None:
                continue
            ordinals.append((patch_ordinal, wid, int(window.region_index)))
            windows.append(color_region.region_window(store, wid))
        if windows:
            plans.append(ColorLanePlan(lane, tuple(windows),
                                       tuple(ordinals),
                                       store.rgb_planes(lane)))
    return tuple(plans)


def local_color_rows(plan: ColorLanePlan, row: FormatRow,
                     geometry: SiteGeometry,
                     certificates: dict) -> dict[int, ColorEvidenceRow]:
    """Run the whole colour head over the covering windows alone.

    `color_region.region_job` is the standing head verbatim — same QDA,
    same detector or CMY7 head, same registration residuals, same
    context matrix, same gates.  Only its window set is local.  Its
    facts are used here and never folded.
    """
    result = color_region.region_job(
        row, geometry, plan.windows, (), plan.planes, certificates,
        color_region.StackConfig(), plan.lane[0], plan.lane[1])
    return {int(fact.patch_ordinal): fact for fact in result.facts
            if isinstance(fact, ColorEvidenceRow)}


def local_color_cut(plan: ColorLanePlan,
                    rows_by_ordinal: dict[int, ColorEvidenceRow],
                    geometry: SiteGeometry, arity: int,
                    cells_yx: tuple[int, int], page: int, ty: int,
                    tx: int) -> tiles.TileCut | None:
    rows = tuple(
        (wid, region_index, rows_by_ordinal[patch_ordinal])
        for patch_ordinal, wid, region_index in plan.ordinals
        if patch_ordinal in rows_by_ordinal)
    if not rows:
        return None
    candidates, order_keys = tiles.color_candidates(
        geometry, arity, page, ty, tx, rows)
    return tiles.assemble_cut(candidates, order_keys, cells_yx,
                              plan.lane[0], plan.lane[1], page, ty, tx)


def _donor_certificates(store: object, page: int,
                        donors: Sequence[TileAddress],
                        ) -> tuple[Certificate, ...]:
    return tuple(
        store.certificate((page, ty, tx, stream.stream_id))
        for ty, tx in donors
        for stream in store.row.streams
        if store.has_certificate((page, ty, tx, stream.stream_id)))


def _k_components(row: FormatRow, geometry: SiteGeometry,
                  plans: Sequence[LanePlan],
                  donor_certs: Sequence[Certificate], page: int, ty: int,
                  tx: int, lookup: object) -> list[tiles.TileCut]:
    printed = refine.certified_fields(row, geometry, donor_certs)
    arity = tiles.evidence_arity(row)
    components: list[tiles.TileCut] = []
    for plan in plans:
        values = tuple(label_values(page, evidence, printed)
                       for _wid, evidence in plan.rows)
        fit = fit_local_context(
            tuple(evidence for _wid, evidence in plan.rows), values)
        if not fit.adopted:
            continue
        cut = local_cut(plan, fit, lookup, arity, row.cells_yx, page, ty, tx)
        if cut is not None:
            components.append(cut)
    return components


def _color_components(row: FormatRow, geometry: SiteGeometry,
                      plans: Sequence[ColorLanePlan], certificates: dict,
                      page: int, ty: int, tx: int) -> list[tiles.TileCut]:
    arity = tiles.evidence_arity(row)
    components: list[tiles.TileCut] = []
    for plan in plans:
        rows_by_ordinal = local_color_rows(plan, row, geometry, certificates)
        if not rows_by_ordinal:
            continue
        cut = local_color_cut(plan, rows_by_ordinal, geometry, arity,
                              row.cells_yx, page, ty, tx)
        if cut is not None:
            components.append(cut)
    return components


def lane_order(components: Sequence[tiles.TileCut],
               ) -> tuple[tiles.TileCut, ...]:
    """The covering lanes in the ONE order this row already has.

    Not a new ordering.  It is `tiles.component_signature`'s key — the
    function that NAMES an attempt, and so decides which attempts are
    the same attempt — and it agrees with `store.cover_lanes`, which
    enumerates captures with `sorted`, and with `tiles._combine`, which
    sums on `capture_id` alone (the same order here, since a lane set
    carries one component per capture).  Reusing it means the row walks
    its lanes in the order the union already summed them, rather than
    carrying a second lane order invented for this pass.

    Deterministic, and identically so at any worker count: `capture_id`
    is a property of the declared capture, not of when a job ran.
    """
    return tuple(sorted(components,
                        key=lambda cut: (cut.capture_id, cut.level_index)))


def attempt_sets(components: Sequence[tiles.TileCut],
                 ) -> tuple[tuple[tiles.TileCut, ...], ...]:
    """The component sets to attempt, in order: the union, then each lane.

    THE MEASURED SHAPE (`measure/local_ab`, sheet I, two corner crops,
    153 armed subjects): per-origin attempts are a strict SUPERSET of
    the union — 6 certificates against the union's 2, zero wrong, and
    the union never won a tile the lanes lost.  The mechanism is the
    multi-scan law at tile scale: `tiles._combine` SUMS the lanes' LLRs,
    so two failing lanes outvote one clean one.  On `I-nw` tile (0, 2)
    one lane certified in 10 belief-propagation iterations while the
    union of all three failed at the ceiling.

    The union still goes FIRST, and stays, because `_combine` does a
    second thing: it UNIONS the observed set.  A lane whose own window
    coverage is thin comes back `below_attempt_floor` where the combined
    observation clears the code's support floor — 10 times across the
    two cases.  So this is additive, not a replacement.

    A SINGLE-LANE subject yields ONE set.  The union IS that lane there,
    so a per-lane pass would re-decode identical evidence under an
    identical attempt key; those tiles see no change whatsoever.
    Components are one-per-lane by construction — `_k_components` and
    `_color_components` append at most one cut per plan, and
    `_lane_plans`/`_color_lane_plans` build one plan per lane — so the
    length of `components` is the lane count.
    """
    ordered = lane_order(components)
    if len(ordered) < 2:
        return (ordered,) if ordered else ()
    return (ordered,) + tuple((cut,) for cut in ordered)


def _attempt(row: FormatRow, geometry: SiteGeometry,
             components: Sequence[tiles.TileCut], page: int, ty: int,
             tx: int, stream_id: str, started: float) -> JobResult:
    """Attempt the union, then the lanes, stopping at the first certificate.

    Every attempt is the same codec gate at the same budget
    (`STAGE_LOCAL150` = 150 iterations) and every one of them is
    reported: an attempt this row makes is an `AttemptFact` and a
    `TileOutcome` like any other, so the per-tool accounting counts what
    was actually spent.  The meter is not touched here — the job body
    started it and this function reads it once, at the end, whether it
    made one attempt or four.

    Stopping at the first certificate is free and monotone: a tile has
    one answer, and the codec gate is what says so.  Measured, it saves
    little (59.9 s against 60.6 s exhaustive on `I-tl`) because
    certificates are rare on a residue — but it costs nothing to take.
    """
    facts: list[object] = []
    events: list[object] = []
    for attempt in attempt_sets(components):
        result = tiles.attempt_tile(row, geometry, attempt, stream_id,
                                    tiles.STAGE_LOCAL150)
        facts.append(result.fact)
        events.append(result.event)
        if result.certificate is not None:
            facts.append(result.certificate)
            break
    return JobResult(tuple(facts), tuple(events),
                     time.thread_time() - started)


def _local_job(row: FormatRow, geometry: SiteGeometry, page: int, ty: int,
               tx: int, stream_id: str,
               build: Callable[[], list[tiles.TileCut]]) -> Job:
    """The one job body both arms share: build components, then attempt."""

    def job() -> JobResult:
        started = time.thread_time()
        components = build()
        return _attempt(row, geometry, components, page, ty, tx, stream_id,
                        started)

    return job


def _prepare_k(store: object, page: int, ty: int, tx: int, stream_id: str,
               ppc: Fraction,
               donors: Sequence[TileAddress]) -> Job | None:
    plans = _lane_plans(store, page, ty, tx, ppc)
    if not plans:
        return None
    donor_certs = _donor_certificates(store, page, donors)
    row = store.row
    geometry = store.geometry
    lookup = store.lookup
    return _local_job(
        row, geometry, page, ty, tx, stream_id,
        lambda: _k_components(row, geometry, plans, donor_certs, page, ty,
                              tx, lookup))


def _prepare_color(store: object, page: int, ty: int, tx: int,
                   stream_id: str, ppc: Fraction) -> Job | None:
    plans = _color_lane_plans(store, page, ty, tx, ppc)
    if not plans:
        return None
    certificates = store.certificates()
    row = store.row
    geometry = store.geometry
    return _local_job(
        row, geometry, page, ty, tx, stream_id,
        lambda: _color_components(row, geometry, plans, certificates, page,
                                  ty, tx))


def prepare_local(store: object, subject: Subject, stage: str) -> Job | None:
    page, ty, tx, stream_id, ppc = subject
    if store.has_certificate((page, ty, tx, stream_id)):
        return None
    donors = certified_neighbours(
        store, page, neighbourhood_tiles(store, page, ty, tx, ppc), (ty, tx))
    if not donors:
        return None
    if store.row.family is Family.K:
        return _prepare_k(store, page, ty, tx, stream_id, ppc, donors)
    return _prepare_color(store, page, ty, tx, stream_id, ppc)


def _local_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    if fact.outcome != tiles.OUTCOME_FAILED:
        return ()
    if fact.stage not in ARMING_STAGES or not fact.components:
        return ()
    ppc = store.level(*fact.components[0]).ppc
    return ((fact.page, fact.ty, fact.tx, fact.stream_id, ppc),)


def _local_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    page, ty, tx, _stream_id, ppc = subject
    keys: list[FactKey] = []
    for lane in store.cover_lanes(page, ty, tx, ppc):
        for wid in covering_windows(store, page, ty, tx, lane):
            keys.append((KEY_EVIDENCE_FIT, wid))
            keys.append((KEY_EVIDENCE_READ, wid))
        for row_key in covering_color_rows(store, page, ty, tx, lane):
            keys.append((KEY_COLOR_ROW,) + tuple(row_key))
    for nty, ntx in neighbourhood_tiles(store, page, ty, tx, ppc):
        for stream in store.row.streams:
            keys.append((KEY_TILE, page, nty, ntx, stream.stream_id))
    return tuple(keys)


def _local_eligible(store: object, subject: Subject) -> bool:
    page, ty, tx, stream_id, ppc = subject
    if store.has_certificate((page, ty, tx, stream_id)):
        return False
    reach = neighbourhood_tiles(store, page, ty, tx, ppc)
    return bool(certified_neighbours(store, page, reach, (ty, tx)))


def _local_retire(store: object, subject: Subject) -> bool:
    page, ty, tx, stream_id, _ppc = subject
    return store.has_certificate((page, ty, tx, stream_id))


def _local_stage(store: object, subject: Subject) -> str | None:
    return STAGE_LOCAL


def _local_cost(store: object, subject: Subject, stage: str, attempts: int,
                last_cost: int) -> int:
    return LOCAL_COST + RUNG_COST * store.union_rung_ordinal(subject[4])


LOCAL_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN,
    subject_kind="tile",
    born_by=(AttemptFact,),
    subjects_of=_local_subjects,
    reads=_local_reads,
    eligible=_local_eligible,
    stage=_local_stage,
    cost=_local_cost,
    retire=_local_retire,
    prepare=prepare_local,
    produces=(AttemptFact, Certificate),
    prices=PRICES,
)

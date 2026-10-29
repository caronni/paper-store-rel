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
detector calibration or the CMY7 head, the registration arm, the
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
(docs/TOOLBOX-INVENTORY §6.13, e029's complete 21-tile residue): zero
certificates from every local arm at
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

from .. import sched_trace
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
    KEY_ATTEMPT,
    KEY_PLANE_FIELD,
    KEY_POSE_AFFINE,
    KEY_TILE,
    PluginDescriptor,
    RETIRE_CERTIFIED,
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

#: THE VERDICTS A RESIDUE ROW SUBSCRIBES TO, which are NOT its arming
#: set (2026-10-03, S9).  A retry exists only after a FAILED scan or
#: union verdict on the same lane and footing (`tiles.arms_retry`), and
#: that verdict already armed the row and already woke it.  The retry's
#: own failed verdict at the same generation carries nothing a residue
#: row reads -- `tiles.local`, `tiles.planek` and `tiles.swim` build
#: their OWN cut -- yet as a read it woke every one of them (sheet J:
#: thousands of attempt-only re-fires, 4 certificates for ~9,950
#: cpu-s).  A retry that CERTIFIES still reaches them, through
#: `KEY_TILE`.  So retry150 stays in the birth and arming sets (a
#: retry failure is a failure: it arms, and the footing ledger keeps
#: it) and leaves the declared reads; `tiles.swim`'s `local150` goes
#: the same way, for the same reason.
READ_STAGES: tuple[str, ...] = (tiles.STAGE_SCAN, tiles.STAGE_UNION)

# The neighbourhood is not a chosen radius: it is exactly the set of
# tiles the windows covering the target tile also cover, read from the
# store.  This bound is what the window grid makes possible — a
# WINDOW_CELLS-wide window straddles at most this many tile boundaries —
# and exists so a test can pin the derivation instead of a constant.
MAX_NEIGHBOUR_TILE_RADIUS: int = -(-(WINDOW_CELLS - 1) // TILE_CELLS)

REASON_NO_LABELS: str = "no_local_labels"

# subject: (page, ty, tx, ppc) -- the tile LANE, one local read per tile
# per printed footing over every capture-lane that covers it there.
#
# It was per tile-STREAM until 2026-09-21, and that was the single
# largest waste in the receiver: the work is a re-fit of the covering
# windows' whole colour head, which is per tile-lane, so the C, M and Y
# siblings of one tile each paid for the IDENTICAL fit.  On the traced
# sheet-H run this row spent 17,627 cpu-s -- 78 % of all job CPU -- for
# 690 certificates, with the three siblings co-firing within five
# seconds of each other 75 % of the time.  One subject, one fit, every
# armed stream decoded off it.
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
    plane_fields: tuple


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


def covering_window_ids(store: object, page: int, ty: int, tx: int,
                        ppc: Fraction) -> tuple[WindowId, ...]:
    """The placed COLOUR windows whose rows cover this tile at this rung.

    The pose of each is a real input to a row that samples the raster
    through it, and this is the narrow spelling of that: four keys
    instead of one `lane_poses` key with 5,880 subscribers.

    An ordinal with no window is SKIPPED, not raised on: this runs
    inside `reads`, on the ENGINE thread, where a KeyError takes the
    run down.  Over-subscribing costs wakes; under-subscribing costs
    one rung -- and neither is worth a crash on a store the colour row
    and the window disagree about (2026-09-21 review).
    """
    wids: list[WindowId] = []
    for lane in store.cover_lanes(page, ty, tx, ppc):
        for row_key in covering_color_rows(store, page, ty, tx, lane):
            try:
                wid = store.window_by_ordinal(lane[0], lane[1],
                                              int(row_key[3]))
            except KeyError:
                continue
            wids.append(wid)
    return tuple(dict.fromkeys(wids))


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


#: THE (stage, lane) PAIRS a residue row's arming verdicts are keyed by,
#: shared by every row that subscribes to them (`tiles.local`,
#: `tiles.planek`, `tiles.swim`).  Each caller spells `KEY_ATTEMPT`
#: itself, so `schedule.read_families` still reports the family.  These
#: are the WAKE keys only: whether a stream is armed is asked of the
#: footing ledger (`_failed_at`), which no lane's departure can empty.
#:
#: A SCAN verdict is always single-lane (`prepare_scan` assembles one
#: cut) and a UNION verdict always summed (`arms_union` demands two
#: captures); every other stage can be either, because its origin can
#: be either.  So scan contributes the lanes, union the footing, and
#: the rest both.
def arming_lanes(store: object, page: int, ty: int, tx: int,
                 ppc: Fraction,
                 stages: Sequence[str]) -> tuple[tuple[str, object], ...]:
    lanes = store.cover_lanes(page, ty, tx, ppc)
    pairs: list[tuple[str, object]] = []
    for stage in stages:
        if stage != tiles.STAGE_UNION:
            pairs.extend((stage, lane) for lane in lanes)
        if stage != tiles.STAGE_SCAN:
            pairs.append((stage, ppc))
    return tuple(pairs)


def _failed_at(store: object, page: int, ty: int, tx: int, stream_id: str,
               stage: str, ppc: Fraction) -> bool:
    """Has this stage EVER failed at this footing?  A failure is the arming,
    and it keeps.

    ONLY A CERTIFICATE DE-ARMS A STREAM, which is base's franchise
    exactly: there a residue bookmark was BORN by the failed verdict
    and lived until the tile certified.  Two narrower readings were
    built and then REFUSED on review (2026-09-21), because
    `attempt_verdict` keeps ONE standing verdict per `(stage, lane)`:
    demanding it be at the tile-lane's CURRENT generation lost the rung
    the moment the evidence moved, and taking the standing verdict at
    any generation lost it the moment a re-read came back
    `below_attempt_floor` -- and this row's `retire` is
    certificate-only, so in both cases the bookmark lived on, never
    eligible, never retired.  Measured on the traced sheet-H run:
    2,667 `attempted_failed -> below_attempt_floor` transitions, and
    seven uncertified tile-streams END that run in that state.

    The 2026-09-21 repair still asked the monotone ledger only at the
    lanes covering the tile NOW (`arming_lanes`), so the same franchise
    was lost through another door: a lane that failed and then LEFT the
    cover (its window's evidence refused, or re-placed elsewhere), with
    the lane that replaced it carrying no failure of its own, left the
    stream unarmed and the bookmark alive (external review, claim 2;
    SCHED-OPEN #5(a)).  Since 2026-10-03 the question is asked of the
    FOOTING ledger: any failure of this stage at this ppc, by whichever
    lane or summed set of lanes, covering or not.  A failure at another
    footing arms that footing's subject, never this one.

    Nor is such a refusal one the evidence justifies: `tiles.local`
    builds its OWN components (`_lane_plans` / `_k_components` /
    `_color_components`), so a cut below `tiles.scan`'s attempt floor
    is not below this row's.  What bounds the re-fires is the version
    floor over the narrow reads, not the arming test.
    """
    return store.attempt_ever_failed_at_footing(page, ty, tx, stream_id,
                                                stage, ppc)


def armed_streams(store: object, page: int, ty: int, tx: int,
                  ppc: Fraction,
                  stages: Sequence[str] = ARMING_STAGES) -> tuple[str, ...]:
    """The streams of this tile-lane a residue fire would be FOR.

    Uncertified, and carrying a failure at this footing from one of the
    stages that arm the row (`_failed_at`: a certificate is the only
    thing that takes a stream out, and a lane leaving the cover is
    not).  Stream order is the format row's, which is a property of the
    coding and not of when anything ran.
    """
    return tuple(
        stream.stream_id for stream in store.row.streams
        if not store.has_certificate((page, ty, tx, stream.stream_id))
        and any(_failed_at(store, page, ty, tx, stream.stream_id, stage,
                           ppc)
                for stage in stages))


#: THE COVER-CHANGE BIRTH FACTS, and the reach repair (2026-10-03;
#: external review claim 3, SCHED-OPEN #5(b)).  A residue row's reads
#: are fixed at birth and grow only on RE-birth (`engine._births`), and
#: the arming verdict is not the only fact that moves what a standing
#: tile-lane reads: a window whose evidence newly covers the tile brings
#: a new lane (its `KEY_ATTEMPT` keys), a colour row brings a new window
#: (its `KEY_POSE_AFFINE`), and either one widens `neighbourhood_tiles`
#: (its reach).  Born by the verdict alone, a bookmark never saw the new
#: lane when that lane's own decode came back below the attempt floor,
#: so a certificate or a pose change there never woke it.
#:
#: These are the only two folds that write the cover and the reach
#: (`_fold_evidence`: `_tile_cover_k` + `_evidence_reach`;
#: `_fold_color_row`: `_tile_cover_color` + `_color_row_cover`).  A
#: `Placement` moves neither -- the evidence taken through it does, and
#: arrives as one of these -- and the ordinal map
#: `covering_window_ids` reads is the `Window` fold's, written before
#: any row can name the ordinal.
COVER_BIRTH_FACTS: tuple[type, ...] = (WindowEvidence, ColorEvidenceRow)


def cover_change_tile_lanes(store: object, fact: object,
                            ) -> tuple[tuple[int, int, int, Fraction], ...]:
    """The tile-lanes `(page, ty, tx, ppc)` this evidence fold covers now.

    Read from the store AFTER the fold (births run after it), so this is
    the fact's NEW cover.  A tile the fact LEFT is not here and need not
    be: leaving shrinks a neighbourhood, and stale keys stay subscribed
    anyway.  Every tile whose neighbourhood the fact widened is one it
    covers -- `neighbourhood_tiles` is the union of the covering windows'
    reach -- so iterating the fact's own cover is complete, and it is
    the cheap spelling: one window's tiles, never the page.
    """
    if isinstance(fact, WindowEvidence):
        covered = store.window_cover_tiles(fact.window_id)
    elif isinstance(fact, ColorEvidenceRow):
        covered = store.color_row_cover_tiles(
            (fact.capture_id, fact.level_index, fact.page,
             fact.patch_ordinal))
    else:
        return ()
    lanes: list[tuple[int, int, int, Fraction]] = []
    for page, ty, tx, capture_id, level_index in covered:
        ppc = store.level(capture_id, level_index).ppc
        lanes.append((int(page), int(ty), int(tx), ppc))
    return tuple(dict.fromkeys(lanes))


def armed_cover_subjects(store: object, fact: object,
                         stages: Sequence[str],
                         ) -> tuple[tuple[tuple[int, int, int, Fraction],
                                          tuple[str, ...]], ...]:
    """The ARMED tile-lanes in this fact's cover, each with its streams.

    A cover change EXTENDS a standing residue bookmark; it never creates
    one.  The filter is what guarantees that in practice: a stream is
    armed only through the footing ledger, and the ledger takes an entry
    only in `_fold_attempt` on a FAILED verdict at `(stage, ppc)`.  The
    first such verdict for a narrow key folds as a change (an unchanged
    fold needs that same failed verdict already standing), and a changed
    AttemptFact runs `_births` -- where this row's own verdict
    `subjects_of`, over the SAME `stages` and the same footing, named
    exactly this tile-lane (and stream).  So the bookmark exists, and
    retire is certificate-only while armed means uncertified, so it is
    live.  Pinned in test_h3_store_wakes.
    """
    subjects: list[tuple[tuple[int, int, int, Fraction],
                         tuple[str, ...]]] = []
    for page, ty, tx, ppc in cover_change_tile_lanes(store, fact):
        armed = armed_streams(store, page, ty, tx, ppc, stages)
        if armed:
            subjects.append(((page, ty, tx, ppc), armed))
    return tuple(subjects)


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
    # the field is the PAGE's, so every lane covering this tile reads
    # the same three cells
    plane_fields = store.page_plane_fields(page)
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
                                       store.rgb_planes(lane),
                                       plane_fields))
    return tuple(plans)


def local_color_rows(plan: ColorLanePlan, row: FormatRow,
                     geometry: SiteGeometry,
                     certificates: dict) -> dict[int, ColorEvidenceRow]:
    """Run the whole colour head over the covering windows alone.

    `color_region.region_job` is the standing head verbatim — same QDA,
    same detector or CMY7 head, the same page fields under the sampler,
    same context matrix, same gates.  Only its window set is local.  Its
    facts are used here and never folded.

    So this row carries NO standing head and owes no refit debt (W8
    R-D): it fits and reads in one breath, from the page field the plan
    was built with, and the fit and the features it is applied to are
    one revision by construction.  The `ColorLaneFit` `region_job`
    emits, revision and all, is dropped with the rest of its facts.
    """
    result = color_region.region_job(
        row, geometry, plan.windows, (), plan.planes, certificates,
        color_region.StackConfig(), plan.lane[0], plan.lane[1],
        plane_fields=plan.plane_fields)
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


@dataclass(frozen=True)
class Generations:
    """The generation to STAMP on each attempt set, keyed as its wake is.

    One fire of this row emits attempts of two shapes -- the summed set
    and one per lane -- and `tiles.attempt_lane` keys their wakes
    differently: the footing's ppc for the summed one, the lane itself
    for a single-component one.  Stamping the footing's generation on
    all of them made every per-lane verdict stale-by-construction at
    its own key (the footing counts every lane's events, so it is
    strictly greater than any one lane's).  Inert while no consumer
    reads a `local150` verdict's generation, and a trap the day one
    does -- `tiles.swim` ARMS on those verdicts (2026-09-21 review).
    `tiles.planek` and `tiles.swim` attempt ONE set, summed or (when a
    single lane produced a cut) one lane, and stamp through `of` too
    since 2026-10-03 (S9).
    """

    union: int = 0
    lanes: tuple[tuple[LaneKey, int], ...] = ()

    def of(self, attempt: Sequence[tiles.TileCut]) -> int:
        if len(attempt) != 1:
            return int(self.union)
        lane = (attempt[0].capture_id, attempt[0].level_index)
        for key, generation in self.lanes:
            if key == lane:
                return int(generation)
        return int(self.union)


def lane_generations(store: object, page: int, ty: int, tx: int,
                     ppc: Fraction) -> Generations:
    """The footing's generation and every covering lane's, read once at
    prepare: what a residue fire stamps through `Generations.of`.  One
    spelling for the three rows that emit both shapes of attempt
    (`tiles.local`, `tiles.planek`, `tiles.swim`)."""
    return Generations(
        union=store.union_generation(page, ty, tx, ppc),
        lanes=tuple(
            (lane, store.tile_lane_generation((page, ty, tx, *lane)))
            for lane in store.cover_lanes(page, ty, tx, ppc)))


def _attempt(row: FormatRow, geometry: SiteGeometry,
             components: Sequence[tiles.TileCut], page: int, ty: int,
             tx: int, stream_ids: Sequence[str], started: float,
             generations: Generations | None = None) -> JobResult:
    """Every armed stream, off ONE build: the union, then the lanes.

    The stream loop is OUTSIDE the attempt-set loop, so the expensive
    half — the local head or context fit, which `build` has already
    done once — is paid once per tile-lane and read by C, M and Y in
    turn.  That is the whole point of the tile-lane subject
    (2026-09-21); before it, three sibling workers each paid for the
    identical fit.

    Every attempt is the same codec gate at the same budget
    (`STAGE_LOCAL150` = 150 iterations) and every one of them is
    reported: an attempt this row makes is an `AttemptFact` and a
    `TileOutcome` like any other, so the per-tool accounting counts what
    was actually spent.  The meter is not touched here — the job body
    started it and this function reads it once, at the end, whether it
    made one attempt or twelve.

    Stopping at the first certificate is free and monotone, and it is
    PER STREAM: a tile-stream has one answer, and the codec gate is what
    says so.  Measured, it saves little (59.9 s against 60.6 s
    exhaustive on `I-tl`) because certificates are rare on a residue —
    but it costs nothing to take.
    """
    facts: list[object] = []
    events: list[object] = []
    stamps = generations or Generations()
    sets = attempt_sets(components)
    for stream_id in stream_ids:
        for attempt in sets:
            result = tiles.attempt_tile(row, geometry, attempt, stream_id,
                                        tiles.STAGE_LOCAL150,
                                        stamps.of(attempt))
            facts.append(result.fact)
            events.append(result.event)
            if result.certificate is not None:
                facts.append(result.certificate)
                break
    return JobResult(tuple(facts), tuple(events),
                     time.thread_time() - started)


def _local_job(row: FormatRow, geometry: SiteGeometry, page: int, ty: int,
               tx: int, stream_ids: Sequence[str],
               build: Callable[[], list[tiles.TileCut]],
               generations: Generations | None = None) -> Job:
    """The one job body both arms share: build components, then attempt."""

    def job() -> JobResult:
        started = time.thread_time()
        components = build()
        return _attempt(row, geometry, components, page, ty, tx, stream_ids,
                        started, generations)

    return job


def _prepare_k(store: object, page: int, ty: int, tx: int,
               stream_ids: Sequence[str], ppc: Fraction,
               donors: Sequence[TileAddress],
               generations: Generations | None = None) -> Job | None:
    plans = _lane_plans(store, page, ty, tx, ppc)
    if not plans:
        return None
    donor_certs = _donor_certificates(store, page, donors)
    row = store.row
    geometry = store.geometry
    lookup = store.lookup
    return _local_job(
        row, geometry, page, ty, tx, stream_ids,
        lambda: _k_components(row, geometry, plans, donor_certs, page, ty,
                              tx, lookup), generations)


def _prepare_color(store: object, page: int, ty: int, tx: int,
                   stream_ids: Sequence[str], ppc: Fraction,
                   generations: Generations | None = None) -> Job | None:
    plans = _color_lane_plans(store, page, ty, tx, ppc)
    if not plans:
        return None
    certificates = store.certificates()
    row = store.row
    geometry = store.geometry
    return _local_job(
        row, geometry, page, ty, tx, stream_ids,
        lambda: _color_components(row, geometry, plans, certificates, page,
                                  ty, tx), generations)


def prepare_local(store: object, subject: Subject, stage: str) -> Job | None:
    page, ty, tx, ppc = subject
    armed = armed_streams(store, page, ty, tx, ppc)
    if not armed:
        return None
    donors = certified_neighbours(
        store, page, neighbourhood_tiles(store, page, ty, tx, ppc), (ty, tx))
    if not donors:
        return None
    # The trace's redundancy PROXY (sched_trace, DEFAULT OFF): this row
    # builds its components inside the job, so digesting the real input
    # would move that work onto the engine thread and change the very
    # number the trace exists to measure.  The donor set and the armed
    # streams are what a re-fire reads differently, so they are what is
    # recorded -- and it is recorded only, never acted on.
    if sched_trace.TRACE.enabled:
        sched_trace.TRACE.note_input(
            "local_donors", (stage, armed, str(ppc),
                             tuple(sorted(repr(donor) for donor in donors))))
    # The GENERATIONS this fire reads, one per attempt set it will
    # emit: reported on every verdict, so a later rung can tell a live
    # verdict from one decoded off evidence that has since moved -- and
    # each stamped on the set whose WAKE KEY it belongs to.
    generations = lane_generations(store, page, ty, tx, ppc)
    if store.row.family is Family.K:
        return _prepare_k(store, page, ty, tx, armed, ppc, donors,
                          generations)
    return _prepare_color(store, page, ty, tx, armed, ppc, generations)


def _local_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    if isinstance(fact, COVER_BIRTH_FACTS):
        return tuple(subject for subject, _armed
                     in armed_cover_subjects(store, fact, ARMING_STAGES))
    if fact.outcome != tiles.OUTCOME_FAILED:
        return ()
    if fact.stage not in ARMING_STAGES or not fact.components:
        return ()
    ppc = store.level(*fact.components[0]).ppc
    return ((fact.page, fact.ty, fact.tx, ppc),)


#: THE CHAIN HEAD'S VERDICTS (`READ_STAGES`), the neighbourhood's
#: certificates, and on colour the page field and the covering windows'
#: poses -- the row's real inputs, and nothing else.  It used to
#: subscribe to the raw evidence rows and colour rows of every covering
#: window, which is what `tiles.scan` reads: routing around its own
#: predecessor's verdict.  Since the chain head is re-armed by every
#: generation bump (INV-G1) and its new verdict is one of these keys,
#: dropping them loses no wake.
#:
#: THE POSES (2026-10-03, S9): the colour arm re-runs the colour head
#: over `color_region.region_window`, which samples the raster through
#: each covering window's `placement.native_affine` -- the same
#: through-the-pose read `tiles.planek` and `tiles.swim` declare, so it
#: is declared the same way.  Before, a pose revision reached this row
#: only if the colour row re-read under it moved the chain head's
#: verdict.  The K arm reads `WindowEvidence` alone (sampled already),
#: so a K pose reaches it as new evidence, i.e. as a new verdict.
def _local_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    page, ty, tx, ppc = subject
    keys: list[FactKey] = []
    if store.row.family is not Family.K:
        keys.extend((KEY_PLANE_FIELD, page, plane) for plane in range(3))
        keys.extend((KEY_POSE_AFFINE, wid)
                    for wid in covering_window_ids(store, page, ty, tx, ppc))
    for stage, lane in arming_lanes(store, page, ty, tx, ppc,
                                    READ_STAGES):
        for stream in store.row.streams:
            keys.append((KEY_ATTEMPT, page, ty, tx, stream.stream_id,
                         stage, lane))
    for nty, ntx in neighbourhood_tiles(store, page, ty, tx, ppc):
        for stream in store.row.streams:
            keys.append((KEY_TILE, page, nty, ntx, stream.stream_id))
    return tuple(keys)


def _local_eligible(store: object, subject: Subject) -> bool:
    page, ty, tx, ppc = subject
    if not armed_streams(store, page, ty, tx, ppc):
        return False
    reach = neighbourhood_tiles(store, page, ty, tx, ppc)
    return bool(certified_neighbours(store, page, reach, (ty, tx)))


#: The MONOTONE half: every stream certified.  A tile-lane with one
#: armed stream left is still live work, and unlike `eligible` this is
#: consulted at every wake.
def _local_retire(store: object, subject: Subject) -> str | None:
    page, ty, tx, _ppc = subject
    return (RETIRE_CERTIFIED
            if all(store.has_certificate((page, ty, tx, stream.stream_id))
                   for stream in store.row.streams) else None)


def _local_stage(store: object, subject: Subject) -> str | None:
    return STAGE_LOCAL


def _local_cost(store: object, subject: Subject, stage: str, attempts: int,
                last_cost: int) -> int:
    """220 on the first fire, plus 220 for every earlier fire of this
    tile-lane, plus the rung.

    The row was priced FLAT until 2026-10-18, so its re-fires -- the
    dearest minting work on every colour sheet measured (fires six and
    up: 1,236 cpu-s per certificate on e046, 2,092 on e042's I, 38-45 %
    of those runs' CPU for 1-3 % of their certificates) -- popped ahead
    of planek's and swim's FIRST fires (7-14 cpu-s per certificate on
    cmy8, 6 on cmy), which waited to the sixth decile of the run.  With
    the escalation every residue row's first fire precedes any row's
    second: 220 < 230 < 240 < 440 (measure/sched_trace/
    YIELD-OVER-CPU-2026-10-18.md §5-6, the owner's balance of
    2026-10-18).  The shape is the one convention for every residue row,
    base + base x earlier fires: a row pays its base once.  Nothing is
    capped -- the row may fire as often as new evidence justifies.
    """
    return (LOCAL_COST + LOCAL_COST * attempts
            + RUNG_COST * store.union_rung_ordinal(subject[3]))


LOCAL_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN,
    subject_kind="tile",
    born_by=(AttemptFact,) + COVER_BIRTH_FACTS,
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

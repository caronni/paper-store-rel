"""``tiles.planek`` — read one printing plane as a black-and-white page.

THE COMPOSITION.  cmy8 is per-plane independent LDPC — format law, not a
convenience — so one plane's stream is a codeword in its own right and
can be decoded alone.  This row builds that stand-alone decoder input:
it isolates the target plane out of the RGB channel means (cancelling
the two sibling planes in the mean, and subtracting them exactly wherever
a certificate or the format proves their bits), hands the result to the
BLACK-AND-WHITE machinery — `calibrate.window_scores`, the PAVA
score-to-probability map, the nine-bin neighbour-count context detector —
and pushes the calibrated LLRs through the UNCHANGED codec at the heavy
BP budget.  Nothing about the format changes; the certificate is minted
by `tiles.attempt_tile` like any other, and zero-wrong is inherited from
that gate.

WHY IT IS A ROW AND NOT A DEFAULT.  The measured record is
`measure/yask` (sheet H, `L:c2-cmy8-r0850-p120-x1@3392x2368`, one to
seven Canon captures, 2026-08-30).  Against a seven-capture production
harvest of the same sheet it recovered **32 yellow tiles the harvest did
not have, zero wrong**, on tiles where the ordinary colour path had
already certified C and M.  The ladder that got there is the shape of
this row:

    raw blue channel                                  0 adds
    + cyan and magenta cancelled in the mean          1
    + per-cell certified-sibling subtraction          5
    + blind per-window sampling offset (dust)        15
    + the ordinary multi-capture union               32

The first line is why the naive reading is not built: magenta darkens
blue by 60% of what yellow does, so the blue channel is a
yellow-plus-magenta readout and reading it raw certifies NOTHING.
`lib/spectral` carries that argument in full.

The same record says the arm is a RESIDUE arm by construction, not a
detector improvement: with the certified neighbours' labels removed it
certifies zero on every crop, even though the isolated signal is
measurably no worse (d' 2.480 against 2.459).  A PAVA map fitted on 120
format sites per tile cannot price 3,976 payload cells.  So eligibility
is `tiles.local`'s shape — uncertified, covered by evidence and a
committed pose, with certified material in the neighbourhood — and the
row prices itself above every other residue row.

PLANE-GENERAL, and cmy8 ONLY.  Yellow off blue is the measured case;
cyan off red and magenta off green are the same arithmetic with a
different column, so the row takes its target plane from the subject's
stream and one code path serves all three.  cmy7 is refused at birth:
its base-7 packing is a JOINT symbol over the three planes and does not
decompose, so there is no per-plane codeword to decode.

TRANSIENT.  Every fit here — the mixing model, the sampling offset, the
PAVA map, the context correction — is built inside the job, used for one
decoder input and dropped.  The row writes no standing evidence row, no
region context cell and no pose; it emits `AttemptFact` and
`Certificate` and nothing else, so the ordinary colour head, the other
tile rows and the close are untouched whatever it decides.

WHAT THIS ROW REUSES, AND WHAT IT OWNS.  The truth at a window's cells is
`color_region.build_window_rows` verbatim (the colour lane's own
furniture-plus-certified-projection evidence).  The sampler is
`calibrate.window_crop` + `calibrate.sample_points`, the two primitives
`calibrate.sampled_window_means` fuses — unfused here because the offset
search reads ONE filtered crop at many point sets.  The calibration is
`calibrate.window_evidence` and `calibrate.apply_region_context`,
unchanged.  The cut is `tiles.color_candidates` + `tiles.assemble_cut`
over transient `ColorEvidenceRow`s.  What this module owns is the
composition and one thing nothing else in holo3 does: choosing a
window's sampling offset BLIND, on the format's own dust sites.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..data import (
    AttemptFact,
    Certificate,
    ColorEvidenceRow,
    JobResult,
    LaneKey,
    PlaneField,
    PlaneRaster,
    Placement,
    WindowEvidence,
    WindowRows,
)
from ..descriptor import (
    FactKey,
    Job,
    KEY_COLOR_ROW,
    KEY_PLANE_FIELD,
    KEY_TILE,
    PluginDescriptor,
    Subject,
)
from ..format.identity import Family, FormatRow, SiteGeometry
from ..lib import plane_field as plane_field_lib
from ..lib import spectral
from ..lib.geometry import TILE_CELLS
from . import calibrate, color_region, local_ctx, tiles
from . import color_region_anchor as anchor

PLUGIN: str = "tiles.planek"
STAGE_PLANEK: str = "planek"

# LATE RESIDUE WORK, and the most expensive kind holo3 has.  One fire
# re-reads every covering window on three channels, searches that
# window's sampling offset over a grid (one filtered crop, many point
# sets, one PAVA fit apiece) and then spends the heavy 150-iteration
# payload attempt — strictly more per tile than `tiles.local` at 220,
# which pays one context fit or one head re-fit plus the same attempt,
# and than `tiles.uplift` at 210/220, which amortises one region
# derivation over a whole lane-page.  It also only ever exists for a
# tile those rows have already failed.  So it queues behind all of them.
PLANEK_COST: int = 230
RUNG_COST: int = 2
PRICES: tuple[tuple[str, int], ...] = ((STAGE_PLANEK, PLANEK_COST),)

# A failed ordinary or retried attempt is what gives this row a subject —
# `tiles.local`'s arming set exactly.  Its own facts never arm it again;
# it re-fires when the covering evidence or a neighbouring certificate
# moves, which is what its declared reads subscribe to.
ARMING_STAGES: tuple[str, ...] = (
    tiles.STAGE_SCAN, tiles.STAGE_UNION, tiles.STAGE_RETRY150)

# The blind sampling-offset grid, in printed DOTS along page +x.  Both
# ends and the step are the measured harness's (`measure/yask`,
# `--shift-min/--shift-max/--shift-step`); the object being searched is
# e033's measured per-plane x-registration sinusoid, 0.83 dot peak and
# ~100 mm period, which +-2 dots covers with room to spare.  The search
# is x-only because that is the axis the sinusoid lives on and the axis
# the yask battery measured; a y arm is unmeasured and unbuilt.
SHIFT_MIN_DOTS: float = -2.0
SHIFT_MAX_DOTS: float = 2.0
SHIFT_STEP_DOTS: float = 0.25

REASON_NO_LANE: str = "no_covering_lane"
REASON_NO_MIX: str = "mix_refused"

TileAddress = tuple[int, int]


def shift_grid() -> tuple[float, ...]:
    """The declared offset candidates, nominal first so a tie keeps it."""
    steps = int(round((SHIFT_MAX_DOTS - SHIFT_MIN_DOTS) / SHIFT_STEP_DOTS))
    grid = [round(SHIFT_MIN_DOTS + index * SHIFT_STEP_DOTS, 6)
            for index in range(steps + 1)]
    return (0.0,) + tuple(value for value in grid if value != 0.0)


@dataclass(frozen=True)
class LanePlan:
    """One capture-level's covering windows, read from the store once."""

    lane: LaneKey
    windows: tuple[color_region.RegionWindow, ...]
    placements: tuple[Placement, ...]
    region_indices: tuple[int, ...]
    planes: tuple[PlaneRaster, PlaneRaster, PlaneRaster]
    #: the standing per-plane registration field for the TARGET plane on
    #: this lane-page, or None when none is published
    field: PlaneField | None


@dataclass
class WindowRead:
    """One window's plane-isolated read at the offset it chose."""

    window: color_region.RegionWindow
    placement: Placement
    region_index: int
    rows: WindowRows
    labels: np.ndarray
    values: np.ndarray
    offset_source: str
    shift_dots: float
    evidence: WindowEvidence | None = None


# --------------------------------------------------------------------
# format truth at a window's cells
# --------------------------------------------------------------------


def plane_labels(rows: WindowRows, plane: int) -> np.ndarray:
    """int8 labels for the black-and-white calibration; -1 = unproven.

    On a K page the 100 word sites of a tile are a BCH codeword under a
    keystream scramble, so labels are about half ones.  On a single
    colour plane they are not: the colour address word renders states
    {0, 3}, whose YELLOW bit is zero at every word site, so a yellow
    read's only furniture marks are the 20 dust sites per tile.  That
    asymmetry is format law and it is why this row needs certified
    neighbours to be useful at all — measured in `measure/yask` §4.3,
    where furniture-only labels certify nothing on any crop.
    """
    bits = np.asarray(rows.known_component_bits, np.uint8)
    known = np.asarray(rows.known_component_mask, bool)
    labels = np.full(bits.shape[0], -1, np.int8)
    proven = known[:, plane]
    labels[proven] = bits[proven, plane]
    return labels


# --------------------------------------------------------------------
# sampling the synthetic plane
# --------------------------------------------------------------------


def field_delta_dots(field: PlaneField | None,
                     page_cells_yx: np.ndarray) -> np.ndarray | None:
    """The standing field's per-cell delta at these cells, or None.

    THE STANDING FIT SPEAKS FIRST.  Where the `fields` row has published
    a registration field for this plane on this lane-page, this row
    samples where that field points and does NOT search: the field is
    fitted from the whole page's certified truth and a per-window scalar
    has no business overruling it.  The blind estimator below covers the
    case the field cannot — no field published, or no support in reach.

    The evaluation and the dots-to-cells conversion are the colour
    lane's own (`color_region.field_offsets` ->
    `anchor.features_with_page_fraction`), so this row samples where the
    standing colour head samples.
    """
    if field is None:
        return None
    cells = np.asarray(page_cells_yx, np.int64)
    support = np.asarray(field.support, np.float64)
    codes = plane_field_lib.tile_codes(cells, support.shape, TILE_CELLS)
    if not np.all(support.ravel()[codes] > 0.0):
        return None
    return plane_field_lib.evaluate(np.asarray(field.delta_dots_xy),
                                   cells, TILE_CELLS)


def offset_points(window: color_region.RegionWindow, cell_dots: int,
                  delta_dots_xy: np.ndarray | None,
                  shift_dots: float) -> np.ndarray:
    """The window's scan points moved by a field delta and an x shift."""
    n_rows = int(np.asarray(window.page_cells_yx).shape[0])
    delta = (np.zeros((n_rows, 2), np.float64) if delta_dots_xy is None
             else np.asarray(delta_dots_xy, np.float64))
    if shift_dots:
        delta = delta + np.asarray((shift_dots, 0.0), np.float64)
    if not np.any(delta):
        return np.asarray(window.scan_points_yx, np.float64)
    return anchor.shifted_points(
        np.asarray(window.scan_points_yx, np.float64),
        anchor.pose_linear(window.affine), delta / cell_dots)


def channel_crops(planes: Sequence[np.ndarray],
                  bound_points: Sequence[np.ndarray],
                  pitch_px: float) -> tuple[calibrate.WindowCrop, ...]:
    """One aperture-filtered crop per channel, covering every point set.

    `calibrate.sampled_window_means` fuses the crop and the read because
    the ordinary path reads one point set.  This row reads many (the
    offset grid), and the crop is the expensive half, so the two
    primitives are used unfused.  The bounds come from the EXTREME point
    sets: the offset enters the scan points affinely, so the bounding box
    of the extremes contains every intermediate candidate.
    """
    shape = (int(planes[0].shape[0]), int(planes[0].shape[1]))
    spanning = np.concatenate([np.asarray(points, np.float64)
                               for points in bound_points])
    return tuple(calibrate.window_crop((planes[channel],), spanning, shape,
                                       pitch_px)
                 for channel in range(spectral.N_PLANES))


def sample_channels(crops: Sequence[calibrate.WindowCrop],
                    points_yx: np.ndarray) -> np.ndarray:
    """(N, 3) aperture-filtered channel means at one point set."""
    return np.stack([calibrate.sample_points(crop, points_yx)
                     for crop in crops], axis=1).astype(np.float64)


def isolated_scores(mix: spectral.PlaneMix, read: WindowRead,
                    values: np.ndarray, plane: int) -> np.ndarray:
    """The synthetic black-on-white luma, in `window_scores` units.

    Ink is DARK, so the synthetic luma is the NEGATED plane presence;
    `window_scores` then removes level and scale exactly as it does for
    a real grey window.
    """
    score = spectral.plane_score(
        mix, values, read.rows.known_component_bits,
        read.rows.known_component_mask, plane)
    return calibrate.window_scores(np.asarray(-score, np.float32))


# --------------------------------------------------------------------
# the blind offset
# --------------------------------------------------------------------


def heldout_loss_at(mix: spectral.PlaneMix, read: WindowRead,
                    values: np.ndarray, plane: int) -> float | None:
    """holo3's own model-selection number for one candidate offset.

    `fit_window_calibration` splits the window's PROVEN labels by site
    parity and reports the log loss of the PAVA map on the half it did
    not see.  Comparing that across offsets compares models on one fixed
    held-out label set — the ordinary use of a held-out score, and blind:
    in a band with no certificate at all the labels are the format's own
    dust states and nothing else.
    """
    fit = calibrate.fit_window_calibration(
        isolated_scores(mix, read, values, plane), read.labels,
        read.rows.page_cells_yx)
    return fit.heldout_logloss if fit.accepted else None


def choose_offset(mix: spectral.PlaneMix, read: WindowRead,
                  planes: Sequence[np.ndarray], cell_dots: int,
                  delta_dots_xy: np.ndarray | None,
                  plane: int) -> WindowRead:
    """Pick this window's sampling offset on its own held-out labels."""
    grid = shift_grid()
    extremes = [offset_points(read.window, cell_dots, delta_dots_xy, shift)
                for shift in (SHIFT_MIN_DOTS, SHIFT_MAX_DOTS, 0.0)]
    shape = (int(planes[0].shape[0]), int(planes[0].shape[1]))
    crops = channel_crops(planes, extremes, read.window.pitch_px)
    best_loss: float | None = None
    for shift in grid:
        points = offset_points(read.window, cell_dots, delta_dots_xy, shift)
        if not calibrate.points_inside_raster(points, shape):
            continue
        values = sample_channels(crops, points)
        loss = heldout_loss_at(mix, read, values, plane)
        if loss is None:
            continue
        if best_loss is None or loss < best_loss:
            best_loss = loss
            read.values = values
            read.shift_dots = float(shift)
            read.offset_source = "blind"
    return read


# --------------------------------------------------------------------
# one lane
# --------------------------------------------------------------------


def read_window(row: FormatRow, geometry: SiteGeometry,
                window: color_region.RegionWindow, placement: Placement,
                region_index: int, planes: Sequence[np.ndarray],
                cell_dots: int, certificates: dict, memo: dict,
                field: PlaneField | None,
                plane: int) -> tuple[WindowRead, np.ndarray | None] | None:
    """Nominal read of one window: truth, labels, channel means."""
    rows = color_region.build_window_rows(row, geometry, window,
                                          certificates, memo)
    if not np.asarray(rows.page_cells_yx).shape[0]:
        return None
    delta = field_delta_dots(field, rows.page_cells_yx)
    points = offset_points(window, cell_dots, delta, 0.0)
    shape = (int(planes[0].shape[0]), int(planes[0].shape[1]))
    if not calibrate.points_inside_raster(points, shape):
        return None
    crops = channel_crops(planes, (points,), window.pitch_px)
    values = sample_channels(crops, points)
    return (WindowRead(window=window, placement=placement,
                       region_index=region_index, rows=rows,
                       labels=plane_labels(rows, plane), values=values,
                       offset_source="field" if delta is not None
                       else "nominal", shift_dots=0.0), delta)


def fit_lane_mix(reads: Sequence[WindowRead]) -> spectral.PlaneMix:
    """The mixing model over every covering window of this lane.

    Lane scope, not window scope: the fit needs cells proven in all three
    planes, and pooling the covering windows is what keeps a window whose
    own certified reach is thin from refusing on class starvation.  It is
    also the measured harness's scope.
    """
    return spectral.fit_plane_mix(
        np.concatenate([read.values for read in reads]),
        np.concatenate([read.rows.known_component_bits for read in reads]),
        np.concatenate([read.rows.known_component_mask for read in reads]))


def calibrated_rows(reads: Sequence[WindowRead], mix: spectral.PlaneMix,
                    plane: int) -> tuple[WindowEvidence, ...]:
    """The PAVA fit per window, then the region context over them all."""
    built = []
    for read in reads:
        scores = isolated_scores(mix, read, read.values, plane)
        built.append(calibrate.window_evidence(
            read.placement, read.rows.page_cells_yx, scores, read.labels))
    corrected, _ctx = calibrate.apply_region_context(tuple(built))
    return corrected


def transient_row(read: WindowRead, evidence: WindowEvidence, plane: int,
                  arity: int) -> ColorEvidenceRow | None:
    """The calibrated plane as a colour evidence row, never emitted.

    The target plane's column carries the calibrated LLRs and the other
    two carry 0.0 — the erasure spelling — so `tiles._attempt_cmy8` reads
    exactly the one stream this row is arming and says nothing at all
    about the two planes it did not read.
    """
    if not evidence.accepted or evidence.heldout_logloss is None:
        return None
    values = np.zeros((int(evidence.page_cells_yx.shape[0]), arity),
                      np.float32)
    values[:, plane] = np.asarray(evidence.printed_llr, np.float32)
    return ColorEvidenceRow(
        capture_id=evidence.capture_id, level_index=evidence.level_index,
        patch_ordinal=read.window.patch_ordinal, page=evidence.page,
        page_cells_yx=np.asarray(evidence.page_cells_yx, np.int64),
        values=values, heldout_logloss=float(evidence.heldout_logloss))


@dataclass(frozen=True)
class LaneRead:
    """One lane's finished plane-isolated evidence, before any address.

    The split is where the cost is.  Everything above — three-channel
    sampling, the mixing fit, the offset search, the PAVA maps and the
    context correction — depends on the LANE and not on which tile is
    being attempted; only the cut below does.  Keeping the two apart
    makes that structure visible, keeps `lane_cut` honest about what it
    re-does per tile, and lets an instrument replay the identical
    arithmetic over many tiles without pretending the row is cheaper
    than it is.
    """

    lane: LaneKey
    mix: spectral.PlaneMix
    rows: tuple[tuple[object, int, ColorEvidenceRow], ...]
    offsets: tuple[tuple[int, str, float], ...]


def lane_read(row: FormatRow, geometry: SiteGeometry, plan: LanePlan,
              certificates: dict, plane: int) -> LaneRead | None:
    """Read one capture-level's windows as a black-and-white page."""
    planes = tuple(raster.open() for raster in plan.planes)
    cell_dots = color_region.cell_dots_of(row)
    memo: dict = {}
    reads: list[WindowRead] = []
    deltas: list[np.ndarray | None] = []
    for window, placement, region_index in zip(
            plan.windows, plan.placements, plan.region_indices, strict=True):
        found = read_window(row, geometry, window, placement, region_index,
                            planes, cell_dots, certificates, memo,
                            plan.field, plane)
        if found is None:
            continue
        read, delta = found
        reads.append(read)
        deltas.append(delta)
    if not reads:
        return None
    mix = fit_lane_mix(reads)
    if not mix.accepted:
        return None
    for read, delta in zip(reads, deltas, strict=True):
        if delta is None:
            choose_offset(mix, read, planes, cell_dots, delta, plane)
    arity = tiles.evidence_arity(row)
    candidate_rows = []
    for read, evidence in zip(reads, calibrated_rows(reads, mix, plane),
                              strict=True):
        transient = transient_row(read, evidence, plane, arity)
        if transient is not None:
            candidate_rows.append(
                (read.window.window_id, read.region_index, transient))
    if not candidate_rows:
        return None
    return LaneRead(
        lane=plan.lane, mix=mix, rows=tuple(candidate_rows),
        offsets=tuple((int(read.window.patch_ordinal), read.offset_source,
                       float(read.shift_dots)) for read in reads))


def cut_of(read: LaneRead, row: FormatRow, geometry: SiteGeometry,
           page: int, ty: int, tx: int) -> tiles.TileCut | None:
    """One tile's cut out of a finished lane read."""
    candidates, order_keys = tiles.color_candidates(
        geometry, tiles.evidence_arity(row), page, ty, tx, read.rows)
    return tiles.assemble_cut(candidates, order_keys, row.cells_yx,
                              read.lane[0], read.lane[1], page, ty, tx)


def lane_cut(row: FormatRow, geometry: SiteGeometry, plan: LanePlan,
             certificates: dict, page: int, ty: int, tx: int,
             plane: int) -> tiles.TileCut | None:
    """One capture-level's plane-isolated cut of one tile."""
    read = lane_read(row, geometry, plan, certificates, plane)
    if read is None:
        return None
    return cut_of(read, row, geometry, page, ty, tx)


# --------------------------------------------------------------------
# the job
# --------------------------------------------------------------------


def attempt_components(row: FormatRow, geometry: SiteGeometry,
                       components: Sequence[tiles.TileCut], stream_id: str,
                       ) -> tuple[tuple[object, ...], tuple[object, ...]]:
    """The one attempt, or nothing when no lane produced a cut.

    Several components are the ordinary MULTI-CAPTURE UNION: one cut per
    capture-level, summed by `tiles._combine` exactly as
    `tiles.prepare_union` sums them.  No new arithmetic — the same
    equal-weight LLR addition the receiver already performs, over
    per-capture context that has already been de-correlated (the F1 o F6
    law).  It is worth the largest single step in the measured ladder:
    15 adds on one capture, 32 over seven.
    """
    if not components:
        return (), ()
    result = tiles.attempt_tile(row, geometry, tuple(components), stream_id,
                                tiles.STAGE_PLANEK150)
    facts: tuple[object, ...] = (
        (result.fact,) if result.certificate is None
        else (result.fact, result.certificate))
    return facts, (result.event,)


def planek_job(row: FormatRow, geometry: SiteGeometry,
               plans: Sequence[LanePlan], certificates: dict, page: int,
               ty: int, tx: int, stream_id: str, plane: int) -> JobResult:
    started = time.thread_time()
    components: list[tiles.TileCut] = []
    for plan in plans:
        cut = lane_cut(row, geometry, plan, certificates, page, ty, tx,
                       plane)
        if cut is not None:
            components.append(cut)
    facts, events = attempt_components(row, geometry, components, stream_id)
    return JobResult(facts, events, time.thread_time() - started)


def target_plane(row: FormatRow, stream_id: str) -> int:
    return int(tiles.stream_fact(row, stream_id).plane)


def lane_plans(store: object, page: int, ty: int, tx: int, ppc: object,
               plane: int) -> tuple[LanePlan, ...]:
    plans: list[LanePlan] = []
    for lane in store.cover_lanes(page, ty, tx, ppc):
        windows: list[color_region.RegionWindow] = []
        placements: list[Placement] = []
        region_indices: list[int] = []
        for row_key in local_ctx.covering_color_rows(store, page, ty, tx,
                                                     lane):
            wid = store.window_by_ordinal(lane[0], lane[1], int(row_key[3]))
            window = store.window(wid)
            placement = store.placement(wid)
            if window is None or placement is None:
                continue
            windows.append(color_region.region_window(store, wid))
            placements.append(placement)
            region_indices.append(int(window.region_index))
        if windows:
            plans.append(LanePlan(
                lane=lane, windows=tuple(windows),
                placements=tuple(placements),
                region_indices=tuple(region_indices),
                planes=store.rgb_planes(lane),
                field=store.plane_field((lane[0], lane[1], page, plane))))
    return tuple(plans)


def prepare_planek(store: object, subject: Subject,
                   stage: str) -> Job | None:
    page, ty, tx, stream_id, ppc = subject
    if store.row.family is not Family.CMY8:
        return None
    if store.has_certificate((page, ty, tx, stream_id)):
        return None
    donors = local_ctx.certified_neighbours(
        store, page, local_ctx.neighbourhood_tiles(store, page, ty, tx, ppc),
        (ty, tx))
    if not donors:
        return None
    plane = target_plane(store.row, stream_id)
    plans = lane_plans(store, page, ty, tx, ppc, plane)
    if not plans:
        return None
    row = store.row
    geometry = store.geometry
    certificates = store.certificates()

    def job() -> JobResult:
        return planek_job(row, geometry, plans, certificates, page, ty, tx,
                          stream_id, plane)

    return job


# --------------------------------------------------------------------
# the descriptor
# --------------------------------------------------------------------


def _planek_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    """cmy8 only, and only from a failed ordinary attempt.

    The family gate lives at BIRTH so the row has no subjects at all on a
    K or cmy7 page: nothing to schedule, nothing to consult, nothing to
    report.  cmy7's joint base-7 packing has no per-plane codeword, so
    there is no composition to attempt there — not a policy, an algebra.
    """
    if store.row.family is not Family.CMY8:
        return ()
    if fact.outcome != tiles.OUTCOME_FAILED:
        return ()
    if fact.stage not in ARMING_STAGES or not fact.components:
        return ()
    ppc = store.level(*fact.components[0]).ppc
    return ((fact.page, fact.ty, fact.tx, fact.stream_id, ppc),)


def _planek_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    page, ty, tx, stream_id, ppc = subject
    plane = target_plane(store.row, stream_id)
    keys: list[FactKey] = []
    for lane in store.cover_lanes(page, ty, tx, ppc):
        for row_key in local_ctx.covering_color_rows(store, page, ty, tx,
                                                     lane):
            keys.append((KEY_COLOR_ROW,) + tuple(row_key))
        keys.append((KEY_PLANE_FIELD, lane[0], lane[1], page, plane))
    for nty, ntx in local_ctx.neighbourhood_tiles(store, page, ty, tx, ppc):
        for stream in store.row.streams:
            keys.append((KEY_TILE, page, nty, ntx, stream.stream_id))
    return tuple(keys)


def _planek_eligible(store: object, subject: Subject) -> bool:
    page, ty, tx, stream_id, ppc = subject
    if store.row.family is not Family.CMY8:
        return False
    if store.has_certificate((page, ty, tx, stream_id)):
        return False
    reach = local_ctx.neighbourhood_tiles(store, page, ty, tx, ppc)
    if not local_ctx.certified_neighbours(store, page, reach, (ty, tx)):
        return False
    return any(local_ctx.covering_color_rows(store, page, ty, tx, lane)
               for lane in store.cover_lanes(page, ty, tx, ppc))


def _planek_retire(store: object, subject: Subject) -> bool:
    page, ty, tx, stream_id, _ppc = subject
    return store.has_certificate((page, ty, tx, stream_id))


def _planek_stage(store: object, subject: Subject) -> str | None:
    return STAGE_PLANEK


def _planek_cost(store: object, subject: Subject, stage: str, attempts: int,
                 last_cost: int) -> int:
    """The escalation door, opened for the same reason `tiles.uplift`
    opened it: a growing certified frontier can wake this row again and
    again on the same tile, and one fire is the most expensive thing the
    receiver does.  Nothing is capped — the row may fire as often as new
    evidence justifies — it just drifts behind cheaper work each time."""
    base = PLANEK_COST * attempts if attempts else PLANEK_COST
    return base + RUNG_COST * store.union_rung_ordinal(subject[4])


PLANEK_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN,
    subject_kind="tile",
    born_by=(AttemptFact,),
    subjects_of=_planek_subjects,
    reads=_planek_reads,
    eligible=_planek_eligible,
    stage=_planek_stage,
    cost=_planek_cost,
    retire=_planek_retire,
    prepare=prepare_planek,
    produces=(AttemptFact, Certificate),
    prices=PRICES,
)

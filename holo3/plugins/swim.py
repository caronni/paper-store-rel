"""``tiles.swim`` — the per-plane local-affine rescue, on the residue.

THE LINE THIS ROW CLOSES.  The colour lane corrects a plane's
registration in two places today.  The historical one is a
page-fraction residual, ``{1, y}`` per plane, fitted from word and dust
anchors.  The standing one is ``plugins/fields`` — a per-tile
translation field, pooled over a two-tile Gaussian, LINEARISED around
the incumbent with half-dot probes and ridged toward zero, published
only when its median says at least a quarter dot.  Both are page-scale
statistics, and both are measured to stop short: the field recovers
about a quarter of a two-dot injection on this tree's own degraded sim,
and on sheet I's single-capture live run it declined to publish Y at
all — the one plane it exists for — because thin evidence pushed the
prediction under its own publication floor.

The swim goes where they stop.  Over the windows covering ONE failed
tile, and for each plane separately, it searches for the full local
affine — translation plus the four linear terms, six parameters per
plane per window, in printed dots — that maximises the likelihood of
the cells whose bits the receiver can PROVE.  No linearisation, no
shrinkage, no smoothing, no publication floor; the search starts from
the standing field's own value at that window (the hint) and is bounded
by the printed format's cell.  The result is used to re-read that tile
alone and attempt it at the heavy budget through the unchanged codec.

WHY THE LABELS ARE THE WHOLE DESIGN.  INDEPENDENT-PLANES section 2.12
(E8) measured the obvious blind loop — decode, rebuild a plane's ink
column from the decoder's OWN final decisions, decode again — and it
failed its pre-registered bar at both geometries: 44% of the oracle's
gain at best, WORSE on the second iteration (25%), no dead tile
certified, three quarters of the first step's motion repeated on the
second.  A loopy graph with no damping, behaving as that predicts.

This row is not that loop, and the difference is not a better
optimiser.  E8's estimate was CIRCULAR: the quantity it fed back was
the very quantity under test, so the objective could be improved by
agreeing with a wrong guess.  Every cell in this row's objective is
PROVEN before the search starts, by one of exactly two routes: the
format's own word and dust furniture, whose three plane bits are a
function of the address and nothing else; and the cargo of NEIGHBOURING
tiles that already hold certificates, re-encoded through the printed
format (the d=27 address, the LDPC syndrome, the CRC and the format
re-encode all passed).  The target tile's own cargo — the bits the
correction will be judged by — takes no part in the objective at all.
So the fit has no fixed point to chase, and the row runs its search
ONCE.  Furniture alone is enough, which is what lets the row work in a
dead band where nothing has certified: the E8 loop had nothing to stand
on there; this one has the format.

THE CORRECTION IS TRANSIENT.  The affines are built inside the job,
handed to the colour head through the `offsets_of` seam for one read of
one tile, and discarded.  No standing cell moves: the row emits
``AttemptFact`` and ``Certificate`` and nothing else, so the ordinary
colour head, the standing fields, the other tile rows and the close are
untouched whatever the search decides.  It is monotone by construction
— it only ever attempts (address, stream) pairs that carry no
certificate — and the zero-wrong audit is the only bar, enforced by the
unchanged codec.

COLOUR ONLY.  A per-PLANE correction relative to the committed pose is
meaningless for K: there is one plane, so any correction to it is a
correction to the pose, and the pose rows (`refine`, `revisit`) own
that.

PRICING.  Dearest row in the tree at 240, times its own fire ordinal.
It does everything ``tiles.local``'s colour arm does at 220 — a whole
local head fit over the covering windows — and adds a bounded raster
search per plane per window in front of it, so it must queue behind
that, not beside it.  The ordinal escalates because a growing certified
frontier re-arms the row with more labels: the second swim of a
stubborn tile is worth trying and the fifth should be drifting behind
cheaper work.  Nothing caps it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from fractions import Fraction

import numpy as np
from scipy import ndimage

from ..data import AttemptFact, Certificate, ColorEvidenceRow, JobResult
from ..data import LaneKey, PlaneRaster, WindowId, WindowRows
from ..descriptor import (
    FactKey,
    Job,
    KEY_COLOR_ROW,
    KEY_LANE_POSES,
    KEY_PLANE_FIELD,
    KEY_TILE,
    PluginDescriptor,
    Subject,
)
from ..format.identity import Family, FormatRow, SiteGeometry
from ..lib import local_affine
from . import color_region, fields, local_ctx, tiles
from . import color_region_anchor as anchor
from .color_sites import cell_dots_of

PLUGIN: str = "tiles.swim"
STAGE_SWIM: str = "swim"

# The dearest row there is: a full local colour head (tiles.local, 220)
# with a per-plane raster search in front of it.
SWIM_COST: int = 240
RUNG_COST: int = 2
PRICES: tuple[tuple[str, int], ...] = ((STAGE_SWIM, SWIM_COST),)

# An ordinary or retried failure arms the row, and so does a failed
# LOCAL read: the swim is what comes after the local head has had its
# turn.  Its own stage is absent, so a swim never re-arms itself.
ARMING_STAGES: tuple[str, ...] = (
    tiles.STAGE_SCAN, tiles.STAGE_UNION, tiles.STAGE_RETRY150,
    tiles.STAGE_LOCAL150)

# THE BOUND, derived from the printed format and not chosen.  One CELL
# of translation is the largest displacement that is still a
# registration error: past it a plane's ink is in the next cell, which
# is an addressing question the pose rows own, and the format's own cell
# states are pseudorandom, so a whole-cell slip scores near zero on the
# objective rather than competing with the truth.  It strictly contains
# the standing field's own two-dot clamp wherever a cell is bigger than
# two dots.  The linear terms get half of it at the window edge
# (lib/local_affine.LINEAR_BOUND_FRACTION), so the worst corner of a
# window stays within one cell of the hint.
def translation_bound_dots(row: FormatRow) -> float:
    return float(cell_dots_of(row))


# The search resolves to a QUARTER of a capture pixel expressed in dots.
# One pixel is the capture's sampling interval; the raster the objective
# reads is uniform-filtered over a 0.7-cell aperture and then bilinearly
# interpolated, so a quarter of a pixel is already well inside one
# interpolation span, where the objective is a smooth quadratic and
# further halving refines arithmetic rather than measurement.
RESOLUTION_PIXELS: float = 0.25


def resolution_dots(pitch_px: float, cell_dots: int) -> float:
    """A quarter capture pixel, in printed dots."""
    pixels_per_dot = float(pitch_px) / float(cell_dots)
    if pixels_per_dot <= 0.0:
        return float(cell_dots)
    return RESOLUTION_PIXELS / pixels_per_dot


# The objective needs a per-state level table before it can score
# anything, so its support floor IS the table's: every state that
# survives `fields.state_levels` carries at least MIN_STATE_CELLS cells,
# and a fit wants the whole alphabet's worth of them.  Below this there
# is no table, not a poor one.
MIN_OBJECTIVE_CELLS: int = fields.N_STATES * fields.MIN_STATE_CELLS
MIN_LIVE_STATES: int = 2

PlaneAffines = tuple[local_affine.Affine | None, ...]


@dataclass(frozen=True)
class WindowFit:
    """One window's per-plane affines, and what they cost to find."""

    patch_ordinal: int
    window: color_region.RegionWindow
    affines: PlaneAffines
    correlations: tuple[float, ...]
    log_likelihoods: tuple[float, ...]
    n_cells: int
    n_evaluations: int

    @property
    def fitted(self) -> bool:
        return any(affine is not None for affine in self.affines)


@dataclass(frozen=True)
class SwimPlan:
    """Everything one lane's swim needs, read from the store once."""

    lane: LaneKey
    windows: tuple[color_region.RegionWindow, ...]
    ordinals: tuple[tuple[int, WindowId, int], ...]
    planes: tuple[PlaneRaster, PlaneRaster, PlaneRaster]
    plane_fields: tuple


def _hint_offsets(plane_fields: tuple,
                  page_cells_yx: np.ndarray) -> tuple[np.ndarray, ...]:
    """The offsets the standing read applies here — the search's start.

    Read through `color_region.field_offsets`, which is the SAME call
    the ordinary colour lane makes, so the hint is by construction
    "where the receiver is sampling this plane today" and the swim's
    correction is measured from there.  A lane with no published field
    hints zero, which is also the ablation arm's start.
    """
    evaluated = color_region.field_offsets(plane_fields, page_cells_yx)
    zero = np.zeros((np.asarray(page_cells_yx).shape[0], 2), np.float64)
    if evaluated is None:
        return (zero, zero.copy(), zero.copy())
    return tuple(
        zero.copy() if entry is None else np.asarray(entry, np.float64)
        for entry in evaluated)


def _sample_candidates(crop: tuple[int, int, np.ndarray],
                       scan_points_yx: np.ndarray,
                       pose_linear: np.ndarray, cell_dots: int, plane: int,
                       offsets_dots_xy: np.ndarray) -> np.ndarray:
    """Sample one plane at K candidate offset fields in one pass.

    ``offsets_dots_xy`` is (K, N, 2) in DOTS, x then y.  Dots reach a
    pose's cell->pixel 2x2 through the one shared conversion — divide by
    `cell_dots`, then `anchor.shifted_points` — which is exactly what
    `features_with_page_fraction` does when it reads a window, so what
    the search scores is what the head will read.  The K candidates are
    stacked into one sampling call rather than moved one at a time.
    """
    y0, x0, filtered = crop
    offsets = np.asarray(offsets_dots_xy, np.float64) / float(cell_dots)
    points = np.stack(tuple(
        anchor.shifted_points(scan_points_yx, pose_linear, candidate)
        for candidate in offsets), axis=0)
    flat = points.reshape(-1, 2) - np.asarray((y0, x0), np.float64)
    sampled = ndimage.map_coordinates(
        filtered[..., plane], flat.T, order=1, mode="nearest",
        output=np.float64)
    return sampled.reshape(offsets.shape[0], offsets.shape[1])


def fit_window(row: FormatRow, geometry: SiteGeometry,
               window: color_region.RegionWindow, certificates: dict,
               planes: anchor.Planes, pitch_px: float, divisor: float,
               plane_fields: tuple) -> WindowFit | None:
    """Search one window's three planes, on the cells it can prove."""
    sites = fields.window_sites(row, geometry, window, certificates)
    if sites is None or sites.page_cells_yx.shape[0] < MIN_OBJECTIVE_CELLS:
        return None
    crop = fields.window_crop(sites, planes, pitch_px, divisor)
    if crop is None:
        return None
    cell_dots = cell_dots_of(row)
    hint = _hint_offsets(plane_fields, sites.page_cells_yx)
    unit = local_affine.unit_coordinates(_local_of(sites, window),
                                         window.shape_yx_cells)
    at_hint = np.stack(tuple(
        _sample_candidates(crop, sites.scan_points_yx, sites.pose_linear,
                           cell_dots, plane, hint[plane][None, :, :])[0]
        for plane in range(fields.N_PLANES)), axis=1)
    levels, live_states = fields.state_levels(sites.states, at_hint)
    if int(np.count_nonzero(live_states)) < MIN_LIVE_STATES:
        return None
    keep = live_states[sites.states]
    if int(np.count_nonzero(keep)) < MIN_OBJECTIVE_CELLS:
        return None
    groups = local_affine.state_groups(sites.states[keep])
    kept_unit = unit[keep]
    kept_points = sites.scan_points_yx[keep]
    bound = translation_bound_dots(row)
    resolution = resolution_dots(pitch_px, cell_dots)
    affines: list[local_affine.Affine | None] = []
    scores: list[float] = []
    likelihoods: list[float] = []
    evaluations = 0
    for plane in range(fields.N_PLANES):
        separation = float(levels[live_states, plane].max()
                           - levels[live_states, plane].min())
        if separation < fields.MIN_SEPARATION:
            affines.append(None)
            scores.append(0.0)
            likelihoods.append(0.0)
            continue
        kept_hint = hint[plane][keep]

        def score(candidates: tuple[local_affine.Affine, ...],
                  plane: int = plane,
                  kept_hint: np.ndarray = kept_hint) -> np.ndarray:
            offsets = np.stack(tuple(
                kept_hint + candidate.offsets_dots_xy(kept_unit)
                for candidate in candidates), axis=0)
            sampled = _sample_candidates(
                crop, kept_points, sites.pose_linear, cell_dots, plane,
                offsets)
            return local_affine.correlation_ratios(groups, sampled)

        result = local_affine.search(
            score, local_affine.Affine.zero(), bound, resolution,
            groups.n_cells)
        evaluations += result.n_evaluations
        # A search that never moved is a REFUSAL, not a zero correction.
        # The distinction is load-bearing: the offsets a refused plane
        # carries are the standing lane's own, which for a plane with no
        # published field is the {1, y} page-fraction residual — and a
        # zero correction would silently replace that residual with
        # nothing at all.
        moved = bool(np.any(result.affine.as_vector()))
        affines.append(result.affine if moved else None)
        scores.append(result.correlation)
        likelihoods.append(result.log_likelihood)
    return WindowFit(patch_ordinal=int(window.patch_ordinal),
                     window=window, affines=tuple(affines),
                     correlations=tuple(scores),
                     log_likelihoods=tuple(likelihoods),
                     n_cells=groups.n_cells, n_evaluations=evaluations)


def _local_of(sites: fields.WindowSites,
              window: color_region.RegionWindow) -> np.ndarray:
    """The window-local cell coordinates of the sites that were kept.

    `fields.window_sites` filters the window's rows to the complete ones
    and keeps only their page cells, so the local coordinates come back
    by subtracting the window's own origin — which is what the page
    cells and local cells differ by, row for row.
    """
    page = np.asarray(window.page_cells_yx, np.int64)
    local = np.asarray(window.local_cells_yx, np.int64)
    origin = page[0] - local[0] if page.shape[0] else np.zeros(2, np.int64)
    return np.asarray(sites.page_cells_yx, np.int64) - origin


def offsets_builder(fits: dict[int, WindowFit],
                    windows: dict[int, color_region.RegionWindow],
                    plane_fields: tuple):
    """The `offsets_of` callable the colour head reads this tile through.

    Position-based, so it cannot misalign with whatever row set the head
    builds for a window: every row is offset by the standing hint plus
    the fitted affine evaluated at that row's own place in the window.
    A plane the search refused is handed back to the standing lane
    untouched — its published field if it has one, its page-fraction
    residual if it has not — so the row is a no-op there by
    construction and not by convention.

    A plane the search DID move carries `hint + affine`, and for a plane
    with no published field that replaces the {1, y} page-fraction
    residual rather than adding to it.  Deliberately: the residual is a
    page-wide two-parameter line fitted from NCC anchors, the swim's
    number is an absolute per-window registration measured on that
    window's own proven cells at a finer resolution than the line's own
    residual scatter, and it is only ever applied when it strictly
    improved the profiled likelihood over the offset the lane was
    already reading at.
    """

    def offsets_of(rows: WindowRows) -> tuple[np.ndarray | None, ...] | None:
        ordinal = int(rows.patch_ordinal)
        window = windows.get(ordinal)
        fit = fits.get(ordinal)
        if window is None:
            return None
        cells = np.asarray(rows.page_cells_yx, np.int64)
        standing = color_region.field_offsets(plane_fields, cells)
        if fit is None or not fit.fitted:
            return standing
        hint = _hint_offsets(plane_fields, cells)
        unit = local_affine.unit_coordinates(
            np.asarray(rows.local_cells_yx, np.int64),
            window.shape_yx_cells)
        out: list[np.ndarray | None] = []
        for plane, affine in enumerate(fit.affines):
            if affine is None:
                out.append(None if standing is None else standing[plane])
                continue
            out.append(hint[plane] + affine.offsets_dots_xy(unit))
        return tuple(out)

    return offsets_of


def swim_components(row: FormatRow, geometry: SiteGeometry,
                    plan: SwimPlan, certificates: dict, page: int, ty: int,
                    tx: int) -> tuple[list[tiles.TileCut], list[WindowFit]]:
    """Fit every covering window, then read the tile through the result."""
    ordered = tuple(sorted(plan.windows,
                           key=lambda window: window.patch_ordinal))
    plane_arrays: anchor.Planes = (plan.planes[0].open(),
                                   plan.planes[1].open(),
                                   plan.planes[2].open())
    pitch_px = float(np.median([window.pitch_px for window in ordered]))
    halo = anchor.window_halo(pitch_px)
    divisor = anchor.native_divisor(tuple(
        anchor.crop_maximum(
            plane_arrays,
            anchor.window_points(window.shape_yx_cells, window.affine),
            halo)
        for window in ordered))
    fits: dict[int, WindowFit] = {}
    reports: list[WindowFit] = []
    for window in ordered:
        fit = fit_window(row, geometry, window, certificates, plane_arrays,
                         pitch_px, divisor, plan.plane_fields)
        if fit is None:
            continue
        reports.append(fit)
        if fit.fitted:
            fits[fit.patch_ordinal] = fit
    if not fits:
        return [], reports
    windows_by_ordinal = {int(window.patch_ordinal): window
                          for window in ordered}
    result = color_region.region_job(
        row, geometry, ordered, (), plan.planes, certificates,
        color_region.StackConfig(), plan.lane[0], plan.lane[1],
        offsets_of=offsets_builder(fits, windows_by_ordinal,
                                   plan.plane_fields))
    rows_by_ordinal = {int(fact.patch_ordinal): fact
                       for fact in result.facts
                       if isinstance(fact, ColorEvidenceRow)}
    if not rows_by_ordinal:
        return [], reports
    arity = tiles.evidence_arity(row)
    cut = local_ctx.local_color_cut(
        local_ctx.ColorLanePlan(plan.lane, plan.windows, plan.ordinals,
                                plan.planes),
        rows_by_ordinal, geometry, arity, row.cells_yx, page, ty, tx)
    return ([] if cut is None else [cut]), reports


def swim_job(row: FormatRow, geometry: SiteGeometry,
             plans: tuple[SwimPlan, ...], certificates: dict, page: int,
             ty: int, tx: int, stream_id: str) -> JobResult:
    started = time.thread_time()
    components: list[tiles.TileCut] = []
    for plan in plans:
        cuts, _reports = swim_components(row, geometry, plan, certificates,
                                         page, ty, tx)
        components.extend(cuts)
    facts: tuple[object, ...] = ()
    events: tuple[object, ...] = ()
    if components:
        result = tiles.attempt_tile(row, geometry, tuple(components),
                                    stream_id, tiles.STAGE_SWIM150)
        facts = ((result.fact,) if result.certificate is None
                 else (result.fact, result.certificate))
        events = (result.event,)
    return JobResult(facts, events, time.thread_time() - started)


def _lane_plans(store: object, page: int, ty: int, tx: int,
                ppc: Fraction) -> tuple[SwimPlan, ...]:
    plans: list[SwimPlan] = []
    for lane in store.cover_lanes(page, ty, tx, ppc):
        ordinals: list[tuple[int, WindowId, int]] = []
        windows: list[color_region.RegionWindow] = []
        for row_key in local_ctx.covering_color_rows(store, page, ty, tx,
                                                     lane):
            patch_ordinal = int(row_key[3])
            wid = store.window_by_ordinal(lane[0], lane[1], patch_ordinal)
            window = store.window(wid)
            if store.placement(wid) is None or window is None:
                continue
            ordinals.append((patch_ordinal, wid, int(window.region_index)))
            windows.append(color_region.region_window(store, wid))
        if windows:
            plans.append(SwimPlan(
                lane=lane, windows=tuple(windows), ordinals=tuple(ordinals),
                planes=store.rgb_planes(lane),
                plane_fields=store.lane_plane_fields(lane[0], lane[1],
                                                     page)))
    return tuple(plans)


def prepare_swim(store: object, subject: Subject, stage: str) -> Job | None:
    page, ty, tx, stream_id, ppc = subject
    if store.row.family is Family.K:
        return None
    if store.has_certificate((page, ty, tx, stream_id)):
        return None
    plans = _lane_plans(store, page, ty, tx, ppc)
    if not plans:
        return None
    certificates = store.certificates()
    row = store.row
    geometry = store.geometry

    def job() -> JobResult:
        return swim_job(row, geometry, plans, certificates, page, ty, tx,
                        stream_id)

    return job


def _swim_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    if store.row.family is Family.K:
        return ()
    if fact.outcome != tiles.OUTCOME_FAILED:
        return ()
    if fact.stage not in ARMING_STAGES or not fact.components:
        return ()
    ppc = store.level(*fact.components[0]).ppc
    return ((fact.page, fact.ty, fact.tx, fact.stream_id, ppc),)


def _swim_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    page, ty, tx, _stream_id, ppc = subject
    keys: list[FactKey] = []
    for lane in store.cover_lanes(page, ty, tx, ppc):
        keys.append((KEY_LANE_POSES, lane[0], lane[1], page))
        for plane in range(fields.N_PLANES):
            keys.append((KEY_PLANE_FIELD, lane[0], lane[1], page, plane))
        for row_key in local_ctx.covering_color_rows(store, page, ty, tx,
                                                    lane):
            keys.append((KEY_COLOR_ROW,) + tuple(row_key))
    for nty, ntx in local_ctx.neighbourhood_tiles(store, page, ty, tx, ppc):
        for stream in store.row.streams:
            keys.append((KEY_TILE, page, nty, ntx, stream.stream_id))
    return tuple(keys)


def _swim_eligible(store: object, subject: Subject) -> bool:
    """Uncertified, colour, and covered by a placed colour window.

    No certified-neighbour clause, deliberately, and that is the whole
    difference from `tiles.local`: FURNITURE is enough to fit on, and
    furniture is a function of the address, so a window in a dead band
    where nothing has ever certified still carries labels.  That is the
    regime this row exists for.
    """
    page, ty, tx, stream_id, ppc = subject
    if store.row.family is Family.K:
        return False
    if store.has_certificate((page, ty, tx, stream_id)):
        return False
    for lane in store.cover_lanes(page, ty, tx, ppc):
        for row_key in local_ctx.covering_color_rows(store, page, ty, tx,
                                                    lane):
            wid = store.window_by_ordinal(lane[0], lane[1],
                                          int(row_key[3]))
            if wid is not None and store.placement(wid) is not None:
                return True
    return False


def _swim_retire(store: object, subject: Subject) -> bool:
    page, ty, tx, stream_id, _ppc = subject
    return store.has_certificate((page, ty, tx, stream_id))


def _swim_stage(store: object, subject: Subject) -> str | None:
    return STAGE_SWIM


def _swim_cost(store: object, subject: Subject, stage: str, attempts: int,
               last_cost: int) -> int:
    base = SWIM_COST * attempts if attempts else SWIM_COST
    return base + RUNG_COST * store.union_rung_ordinal(subject[4])


SWIM_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN,
    subject_kind="tile",
    born_by=(AttemptFact,),
    subjects_of=_swim_subjects,
    reads=_swim_reads,
    eligible=_swim_eligible,
    stage=_swim_stage,
    cost=_swim_cost,
    retire=_swim_retire,
    prepare=prepare_swim,
    produces=(AttemptFact, Certificate),
    prices=PRICES,
)

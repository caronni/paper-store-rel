"""``tiles.swim`` — the per-plane local-affine rescue, on the residue.

THE LINE THIS ROW CLOSES.  The colour lane corrects a plane's
registration in one place: ``plugins/fields``, the page's per-tile
translation field, pooled over a two-tile Gaussian and evaluated per
cell.  It is a page-scale statistic and it is measured to stop short —
what a correlation tier can measure is bounded by its own search
radius, so past about 2.2 dots the tiers refuse and the field reads
zero; the swim's own existence stimulus was re-derived to 4.5 dots on
2026-09-03 (conversion_docs/MEASUREMENTS-2026-09-03.md).

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
correction to the pose, and the pose rows (`refine`, `refine.color`) own
that.

THE SUBJECT IS THE TILE-LANE, (page, ty, tx, ppc), since 2026-10-03.
Everything a fire builds — the lane plans, the certificate snapshot,
the plane fields, the per-plane affine search over every covering
window (which already loops over all three planes) and the colour head
read through it — is independent of the stream; a stream id reaches the
work only at `tiles.attempt_tile`.  Per tile-STREAM, the C, M and Y
siblings of one tile each paid for that identical construction, which
is exactly the shape `tiles.local` had before LIFECYCLE row 15 batched
it.  So the row now reads the same way `tiles.local` does: one build
per tile-lane, one attempt per ARMED uncertified stream
(`local_ctx.armed_streams` over this row's own `ARMING_STAGES`), one
`AttemptFact` (and at most one `Certificate`) per stream, and retirement
only when no stream of the tile is left uncertified.  `tiles.planek`
does NOT follow: its search is genuinely per plane.

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
from typing import Sequence

import numpy as np
from scipy import ndimage

from .. import sched_trace
from ..data import AttemptFact, Certificate, ColorEvidenceRow, JobResult
from ..data import LaneKey, PlaneRaster, WindowId, WindowRows
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
from ..lib import local_affine, page_map
from . import color_region, fields_collect, local_ctx, tiles
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
# objective rather than competing with the truth.  The linear terms get
# half of it at the window edge
# (lib/local_affine.LINEAR_BOUND_FRACTION), so the worst corner of a
# window stays within one cell of the hint.
#
# CORRECTED 2026-09-08 (W7): this bound does NOT contain the field's own
# measurement reach, and on a c2 row it never did.  The reach is the
# widest tier radius on the plane less the saturation margin
# (`field_tiers.measurement_reach_dots`) — 2.24 dots on Y against a c2
# bound of 2.0 — and with the certified tier's radius at 1.25 printed
# cells it is 1.25*cell - 0.26 on every row, past one cell everywhere.
# The two bound different things: this one bounds a per-window AFFINE
# against the addressing question, the reach bounds what a correlation
# could have seen.  What licenses the swim is not an ordering but the
# measured column in `test_h3_plugins_swim`: at three dots on a c3 row
# the field reads exactly zero and the search recovers 3.000 of it.
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


#: The per-state cell floor for the level table below.  It came here
#: 2026-09-07 with the page field: the row's objective was the last
#: consumer of the level table once the registration field's linearised
#: photometric tier retired, so the floor lives beside the only thing
#: that reads it.
MIN_STATE_CELLS: int = 8
#: A plane whose ink never moves the channel by this much of full scale
#: is dead here (the M281's starved Y): refuse rather than fit noise.
MIN_SEPARATION: float = 0.02
MIN_LIVE_STATES: int = 2


def min_objective_cells(row: FormatRow) -> int:
    """The objective's support floor, the level table's own.

    The objective needs a per-state level table before it can score
    anything, so its floor IS the table's: every state that survives
    `state_levels` carries at least MIN_STATE_CELLS cells, and a fit
    wants the whole ALPHABET's worth of them — the row's, since
    2026-10-12 (CMY-DESIGN §7 (g)): cmy8's eight states 64 cells, as
    before, cmy's four 32.  Below this there is no table, not a poor
    one.
    """
    return len(row.state_ids) * MIN_STATE_CELLS


def state_levels(states: np.ndarray, values: np.ndarray,
                 state_ids: Sequence[int],
                 min_cells: int = MIN_STATE_CELLS,
                 ) -> tuple[np.ndarray, np.ndarray]:
    """Median sampled value per (state, channel), and which states hold.

    The expected value of a cell depends on all three planes' ink, so
    the prediction is a per-state level table read off the window's own
    complete cells — no channel model, no oracle.  One row per state of
    the row's alphabet (`row.state_ids`, presence ids, in its order):
    cmy8's 0..7 index themselves, cmy's (0, 1, 2, 4) are rows 0..3.
    """
    ids = tuple(int(state) for state in state_ids)
    levels = np.zeros((len(ids), fields_collect.N_PLANES), np.float64)
    live = np.zeros(len(ids), bool)
    for index, state in enumerate(ids):
        selected = states == state
        if int(np.count_nonzero(selected)) < min_cells:
            continue
        levels[index] = np.median(values[selected], axis=0)
        live[index] = True
    return levels, live


def alphabet_index(state_ids: Sequence[int],
                   states: np.ndarray) -> np.ndarray:
    """Each presence id's row in `state_levels`' table."""
    ids = np.asarray(tuple(state_ids), np.int64)
    index = np.full(int(ids.max()) + 1, -1, np.int64)
    index[ids] = np.arange(ids.size, dtype=np.int64)
    rows = index[np.asarray(states, np.int64)]
    if rows.size and rows.min() < 0:
        raise ValueError(f"state outside the alphabet {tuple(state_ids)}")
    return rows

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

    PAGE-axis dots, read through `color_region.field_offsets`, which is
    the SAME call the ordinary colour lane makes, so the hint is by
    construction "where the receiver is sampling this plane today" and
    the swim's correction is measured from there.  A page with no
    solved field hints zero, which is also the ablation arm's start.
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
                       page_linear: np.ndarray, cell_dots: int, plane: int,
                       offsets_dots_xy: np.ndarray) -> np.ndarray:
    """Sample one plane at K candidate offset fields in one pass.

    ``offsets_dots_xy`` is (K, N, 2) in PAGE-axis DOTS, x then y, and
    reaches pixels through `lib/page_map` — which is exactly what
    `anchor.features_at` does when it reads a window, so what the search
    scores is what the head will read.  The K candidates are stacked
    into one sampling call rather than moved one at a time.
    """
    y0, x0, filtered = crop
    offsets = np.asarray(offsets_dots_xy, np.float64)
    points = np.stack(tuple(
        page_map.raster_points(scan_points_yx, page_linear, candidate,
                               cell_dots)
        for candidate in offsets), axis=0)
    flat = points.reshape(-1, 2) - np.asarray((y0, x0), np.float64)
    sampled = ndimage.map_coordinates(
        filtered[..., plane], flat.T, order=1, mode="nearest",
        output=np.float64)
    return sampled.reshape(offsets.shape[0], offsets.shape[1])


@dataclass(frozen=True)
class WindowSites:
    """The cells of one window whose three plane bits are all known.

    This row's, and only this row's: its objective is a per-STATE local
    affine, so it needs all three planes at a cell to know the state.
    The page field's collector measures one plane at a time against that
    plane's own template and takes its cells from the window pose
    directly, which is why the intersection lives here and moved out of
    `fields_collect` with W8 (external review F3).

    Deliberately carries no raster: a capture-page can own a hundred
    windows, and holding each one's filtered crop for the length of a
    job would cost gigabytes on a real sheet.

    Both cell frames come from the rows the window built, never one
    inferred from the other: page and local differ by a ROTATION on a
    placed scrap, and a reader that recovered one by subtracting an
    origin would be right only at rot 0.
    """

    page_cells_yx: np.ndarray
    local_cells_yx: np.ndarray
    states: np.ndarray
    scan_points_yx: np.ndarray
    window: color_region.RegionWindow


def window_sites(row: FormatRow, geometry: SiteGeometry,
                 window: color_region.RegionWindow,
                 certificates: dict,
                 memo: dict[tuple[int, int, int],
                            color_region.Projection | None] | None = None,
                 ) -> WindowSites | None:
    """One window's cells whose state is known in all three planes.

    `memo` is the certified-projection cache; passing one dictionary
    through every window of a job re-encodes each certified tile once
    instead of once per covering window.
    """
    rows = color_region.build_window_rows(
        row, geometry, window, certificates,
        {} if memo is None else memo)
    complete = np.flatnonzero(
        np.asarray(rows.known_component_mask, bool).all(axis=1))
    if not complete.size:
        return None
    return WindowSites(
        page_cells_yx=np.asarray(rows.page_cells_yx, np.int64)[complete],
        local_cells_yx=np.asarray(rows.local_cells_yx,
                                  np.int64)[complete],
        states=np.asarray(rows.states, np.int64)[complete],
        scan_points_yx=np.asarray(rows.scan_points_yx,
                                  np.float64)[complete],
        window=window)


def fit_window(row: FormatRow, geometry: SiteGeometry,
               window: color_region.RegionWindow, certificates: dict,
               planes: anchor.Planes, pitch_px: float, divisor: float,
               plane_fields: tuple) -> WindowFit | None:
    """Search one window's three planes, on the cells it can prove."""
    sites = window_sites(row, geometry, window, certificates)
    floor = min_objective_cells(row)
    if sites is None or sites.page_cells_yx.shape[0] < floor:
        return None
    crop = fields_collect.window_crop(sites.window, planes, pitch_px,
                                     divisor)
    if crop is None:
        return None
    cell_dots = cell_dots_of(row)
    hint = _hint_offsets(plane_fields, sites.page_cells_yx)
    unit = local_affine.unit_coordinates(sites.local_cells_yx,
                                         window.shape_yx_cells)
    at_hint = np.stack(tuple(
        _sample_candidates(crop, sites.scan_points_yx, window.page_linear,
                           cell_dots, plane, hint[plane][None, :, :])[0]
        for plane in range(fields_collect.N_PLANES)), axis=1)
    levels, live_states = state_levels(sites.states, at_hint,
                                       row.state_ids)
    if int(np.count_nonzero(live_states)) < MIN_LIVE_STATES:
        return None
    keep = live_states[alphabet_index(row.state_ids, sites.states)]
    if int(np.count_nonzero(keep)) < floor:
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
    for plane in range(fields_collect.N_PLANES):
        separation = float(levels[live_states, plane].max()
                           - levels[live_states, plane].min())
        if separation < MIN_SEPARATION:
            affines.append(None)
            scores.append(0.0)
            likelihoods.append(0.0)
            continue
        # THE SEARCH SPACE IS THE WINDOW'S OWN.  A local affine's
        # translation and linear terms are dots along this window's
        # cell axes, and its unit coordinates are window-local, so the
        # page-axis hint comes DOWN into that frame to be composed with
        # a candidate and the sum goes back UP into page axes to be
        # sampled — which is the frame every reader of a field speaks.
        kept_hint = page_map.local_axes(hint[plane][keep], window.rotation)

        def score(candidates: tuple[local_affine.Affine, ...],
                  plane: int = plane,
                  kept_hint: np.ndarray = kept_hint) -> np.ndarray:
            offsets = np.stack(tuple(
                page_map.page_axes(
                    kept_hint + candidate.offsets_dots_xy(kept_unit),
                    window.rotation)
                for candidate in candidates), axis=0)
            sampled = _sample_candidates(
                crop, kept_points, window.page_linear, cell_dots, plane,
                offsets)
            return local_affine.correlation_ratios(groups, sampled)

        result = local_affine.search(
            score, local_affine.Affine.zero(), bound, resolution,
            groups.n_cells)
        evaluations += result.n_evaluations
        # A search that never moved is a REFUSAL, not a zero correction.
        # The distinction is load-bearing: the offsets a refused plane
        # carries are the page's own standing field, and a zero
        # correction would silently replace that field with nothing at
        # all wherever the search simply had nothing to add.
        moved = bool(np.any(result.affine.as_vector()))
        affines.append(result.affine if moved else None)
        scores.append(result.correlation)
        likelihoods.append(result.log_likelihood)
    return WindowFit(patch_ordinal=int(window.patch_ordinal),
                     window=window, affines=tuple(affines),
                     correlations=tuple(scores),
                     log_likelihoods=tuple(likelihoods),
                     n_cells=groups.n_cells, n_evaluations=evaluations)


def offsets_builder(fits: dict[int, WindowFit],
                    windows: dict[int, color_region.RegionWindow],
                    plane_fields: tuple):
    """The `offsets_of` callable the colour head reads this tile through.

    Position-based, so it cannot misalign with whatever row set the head
    builds for a window: every row is offset by the standing hint plus
    the fitted affine evaluated at that row's own place in the window.
    A plane the search refused is handed back to the standing page
    untouched — its solved field if that plane has one, nothing if it
    has not — so the row is a no-op there by construction and not by
    convention.

    A WINDOW this seam has nothing to say about answers with a tuple of
    per-plane Nones, never the page-level `None` `field_offsets` returns:
    that one means "no plane of this page is solved anywhere" and takes
    the region's whole corrected arm away with it, which is right for the
    ordinary lane and wrong here, where the fitted windows' corrections
    would go with it.  Read at the pose, keep the arm.

    A plane the search DID move carries `hint + affine`, composed in
    the window's own frame and handed back in PAGE axes, because that
    is the unit `row_offsets` and `anchor.features_at` consume.  The
    swim's number is an absolute per-window registration measured on
    that window's own proven cells, at a finer resolution than the
    page-scale field's own tile grid, and it is only ever applied when
    it strictly improved the profiled likelihood over the offset the
    lane was already reading at.
    """

    at_the_pose: tuple[np.ndarray | None, ...] = (
        (None,) * fields_collect.N_PLANES)

    def offsets_of(rows: WindowRows) -> tuple[np.ndarray | None, ...]:
        ordinal = int(rows.patch_ordinal)
        window = windows.get(ordinal)
        fit = fits.get(ordinal)
        if window is None:
            return at_the_pose
        cells = np.asarray(rows.page_cells_yx, np.int64)
        standing = color_region.field_offsets(plane_fields, cells)
        if fit is None or not fit.fitted:
            return at_the_pose if standing is None else standing
        hint = _hint_offsets(plane_fields, cells)
        unit = local_affine.unit_coordinates(
            np.asarray(rows.local_cells_yx, np.int64),
            window.shape_yx_cells)
        out: list[np.ndarray | None] = []
        for plane, affine in enumerate(fit.affines):
            if affine is None:
                out.append(None if standing is None else standing[plane])
                continue
            local = page_map.local_axes(hint[plane], window.rotation)
            out.append(page_map.page_axes(
                local + affine.offsets_dots_xy(unit), window.rotation))
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
                                plan.planes, plan.plane_fields),
        rows_by_ordinal, geometry, arity, row.cells_yx, page, ty, tx)
    return ([] if cut is None else [cut]), reports


def swim_job(row: FormatRow, geometry: SiteGeometry,
             plans: tuple[SwimPlan, ...], certificates: dict, page: int,
             ty: int, tx: int, stream_ids: Sequence[str],
             generations: local_ctx.Generations | None = None,
             ) -> JobResult:
    """Every armed stream, off ONE build: fit and read once, then attempt.

    The construction — every covering window's three-plane search and
    the colour head read through it — is stream-independent and is paid
    once per tile-lane; the stream loop sits OUTSIDE it, exactly as in
    `local_ctx._attempt`.  Each stream gets one attempt at the heavy
    budget and its own verdict: an `AttemptFact` always, a `Certificate`
    beside it when the codec gate passes.  A stream's certificate ends
    that stream only — the others are read off the same cut.  No cut at
    all (no window fitted, or the head returned nothing) is no attempt
    for any stream, as before.
    """
    started = time.thread_time()
    components: list[tiles.TileCut] = []
    for plan in plans:
        cuts, _reports = swim_components(row, geometry, plan, certificates,
                                         page, ty, tx)
        components.extend(cuts)
    facts: list[object] = []
    events: list[object] = []
    # A one-lane attempt is keyed by its lane, so it carries that lane's
    # generation, not the footing's (`local_ctx.Generations`, 2026-10-03).
    generation = (generations or local_ctx.Generations()).of(components)
    if components:
        for stream_id in stream_ids:
            result = tiles.attempt_tile(row, geometry, tuple(components),
                                        stream_id, tiles.STAGE_SWIM150,
                                        generation)
            facts.append(result.fact)
            events.append(result.event)
            if result.certificate is not None:
                facts.append(result.certificate)
    return JobResult(tuple(facts), tuple(events),
                     time.thread_time() - started)


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
                plane_fields=store.page_plane_fields(page)))
    return tuple(plans)


def _note_swim_inputs(store: object, page: int, ty: int, tx: int,
                      ppc: Fraction, stage: str, armed: Sequence[str],
                      plans: Sequence[SwimPlan]) -> None:
    """The trace's redundancy PROXY (sched_trace, DEFAULT OFF).

    Recorded, never acted on.  This row builds its fit inside the job,
    so digesting the real input — the assembled cut — would move that
    work onto the engine thread and change the very number the trace
    exists to measure.  What a re-fire reads differently is the
    covering windows and their poses, the page field's revision and the
    labels the objective may stand on (the certified tile-streams of the
    neighbourhood), so that is the digest; `bare_parts` drops the stage
    and the armed streams so a re-fire whose armed set shrank, over the
    same evidence, still joins its predecessor.
    """
    if not sched_trace.TRACE.enabled:
        return
    # `_lane_plans` keeps placed windows only, so every pose is there.
    windows = tuple(
        (repr(plan.lane), tuple(
            (int(ordinal), repr(wid),
             tuple(store.placement(wid).native_affine))
            for ordinal, wid, _region in plan.ordinals))
        for plan in plans)
    labels = tuple(
        (nty, ntx, stream.stream_id)
        for nty, ntx in local_ctx.neighbourhood_tiles(store, page, ty, tx,
                                                      ppc)
        for stream in store.row.streams
        if store.has_certificate((page, nty, ntx, stream.stream_id)))
    bare = (str(ppc), windows, int(store.field_revision(page)), labels)
    sched_trace.TRACE.note_input("swim_inputs",
                                 (stage, tuple(armed), *bare),
                                 bare_parts=bare)


def prepare_swim(store: object, subject: Subject, stage: str) -> Job | None:
    """One job per tile-lane, for the streams armed and uncertified NOW.

    The armed set is read here, on the engine thread, so a stream that
    certified before this prepare is not attempted.  One that certifies
    between this prepare and the job's merge IS attempted — the job
    cannot see the store — and its verdict folds as any late verdict
    does; a second certificate for it is refused by
    `_fold_certificate`'s own rule (identical user bits: no change, no
    key; different bits: an `IntegrityError`, which the codec's d=27 /
    LDPC / CRC gates make a format-law event, not a scheduling one).
    """
    page, ty, tx, ppc = subject
    if store.row.family is Family.K:
        return None
    armed = local_ctx.armed_streams(store, page, ty, tx, ppc, ARMING_STAGES)
    if not armed:
        return None
    plans = _lane_plans(store, page, ty, tx, ppc)
    if not plans:
        return None
    _note_swim_inputs(store, page, ty, tx, ppc, stage, armed, plans)
    certificates = store.certificates()
    row = store.row
    geometry = store.geometry
    # The GENERATIONS this fire reads, keyed as its verdict's wake is:
    # reported on every verdict it emits, so a later rung can tell a
    # live verdict from one decoded off evidence that has since moved.
    generations = local_ctx.lane_generations(store, page, ty, tx, ppc)

    def job() -> JobResult:
        return swim_job(row, geometry, plans, certificates, page, ty, tx,
                        armed, generations)

    return job


def _swim_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    """The tile-LANE a failed colour verdict arms — one for C, M and Y.

    A colour row or an evidence row is the reach repair's re-birth
    (`local_ctx.COVER_BIRTH_FACTS`): only tile-lanes in its cover this
    row's stages already ARMED, so it extends a standing bookmark and
    never creates one.
    """
    if store.row.family is Family.K:
        return ()
    if isinstance(fact, local_ctx.COVER_BIRTH_FACTS):
        return tuple(subject for subject, _armed
                     in local_ctx.armed_cover_subjects(store, fact,
                                                       ARMING_STAGES))
    if fact.outcome != tiles.OUTCOME_FAILED:
        return ()
    if fact.stage not in ARMING_STAGES or not fact.components:
        return ()
    ppc = store.level(*fact.components[0]).ppc
    return ((fact.page, fact.ty, fact.tx, ppc),)


#: THE `lane_poses` STORM, ended.  W9/R5 gave this row the page-wide
#: lane-pose key because the swim samples the raster THROUGH the
#: placement, and that argument is ANSWERED rather than waived here:
#: `_fold_placement` emits `pose_affine` and `lane_poses` at the same
#: site under the same `affine_changed` test, so the per-window key is
#: the SAME wake -- at four keys instead of one with 5,880 subscribers.
#: Measured on sheet H: 4,901,310 of the run's 6,552,379 wakes (74.8 %)
#: reached this row, for 19 fires and 1 certificate.
#:
#: The colour rows go the same way as `tiles.planek`'s: they are the
#: chain head's reads, and the head's verdict is subscribed to directly.
#:
#: The arming verdicts are subscribed for EVERY stream of the tile-lane:
#: any one of them failing is a stream this subject now owes a read.
#: Only the chain head's, though (`local_ctx.READ_STAGES`, 2026-10-03):
#: a retry150 or local150 failure follows a scan or union failure that
#: already armed and woke this row, and its cut is not the one this row
#: builds, so it arms (`ARMING_STAGES`) without waking.
def _swim_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    page, ty, tx, ppc = subject
    keys: list[FactKey] = [(KEY_PLANE_FIELD, page, plane)
                           for plane in range(fields_collect.N_PLANES)]
    for stage, lane in local_ctx.arming_lanes(store, page, ty, tx, ppc,
                                              local_ctx.READ_STAGES):
        for stream in store.row.streams:
            keys.append((KEY_ATTEMPT, page, ty, tx, stream.stream_id,
                         stage, lane))
    for wid in local_ctx.covering_window_ids(store, page, ty, tx, ppc):
        keys.append((KEY_POSE_AFFINE, wid))
    for nty, ntx in local_ctx.neighbourhood_tiles(store, page, ty, tx, ppc):
        for stream in store.row.streams:
            keys.append((KEY_TILE, page, nty, ntx, stream.stream_id))
    return tuple(keys)


def _swim_eligible(store: object, subject: Subject) -> bool:
    """Colour, an armed uncertified stream, and a placed colour window.

    No certified-neighbour clause, deliberately, and that is the whole
    difference from `tiles.local`: FURNITURE is enough to fit on, and
    furniture is a function of the address, so a window in a dead band
    where nothing has ever certified still carries labels.  That is the
    regime this row exists for.

    The arming clause is `local_ctx.armed_streams` over this row's own
    stages: uncertified, and failed at this footing by one of them.  A
    certificate is the only thing that takes a stream out.
    """
    page, ty, tx, ppc = subject
    if store.row.family is Family.K:
        return False
    if not local_ctx.armed_streams(store, page, ty, tx, ppc, ARMING_STAGES):
        return False
    for lane in store.cover_lanes(page, ty, tx, ppc):
        for row_key in local_ctx.covering_color_rows(store, page, ty, tx,
                                                    lane):
            wid = store.window_by_ordinal(lane[0], lane[1],
                                          int(row_key[3]))
            if wid is not None and store.placement(wid) is not None:
                return True
    return False


#: The MONOTONE half, certificate-only: every stream of the tile
#: certified.  A tile-lane with one stream left is still live work.
def _swim_retire(store: object, subject: Subject) -> str | None:
    page, ty, tx, _ppc = subject
    return (RETIRE_CERTIFIED
            if all(store.has_certificate((page, ty, tx, stream.stream_id))
                   for stream in store.row.streams) else None)


def _swim_stage(store: object, subject: Subject) -> str | None:
    return STAGE_SWIM


def _swim_cost(store: object, subject: Subject, stage: str, attempts: int,
               last_cost: int) -> int:
    """240 on the first fire, plus 240 for every earlier fire, plus the
    rung (2026-10-18: base + base x earlier fires, the one convention for
    every residue row; until then the first two fires both cost 240).

    `attempts` counts TILE-LANE fires since 2026-10-03 (one fire reads
    every armed stream), so a tile whose C, M and Y each failed pays
    the escalation once, not three times over in parallel.
    """
    base = SWIM_COST + SWIM_COST * attempts
    return base + RUNG_COST * store.union_rung_ordinal(subject[3])


SWIM_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN,
    subject_kind="tile",
    born_by=(AttemptFact,) + local_ctx.COVER_BIRTH_FACTS,
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

"""The `fields` row: fit a per-plane registration field from the page's
own certified truth.

Subject is the colour LANE-PAGE (capture, level, page) — the unit the
colour lane itself assembles on and the unit certificates are keyed by.
The row is born by Certificate folds, re-fires as certified reach grows
(it subscribes to the page's certificates and to the lane's poses), and
prices its own re-fits by fire ordinal so a page that certifies in a
hundred batches does not re-fit a hundred times at a flat price.

Evidence is the format truth the receiver already holds for a cell:
every word/dust site of an addressed tile, plus every payload cell of a
tile whose three streams are certified.  For each such cell the job
samples the plane's own channel at the committed pose and at four
half-dot probes around it, which turns "how far is this plane off here"
into two linear equations per cell.  `lib/plane_field` does the rest.

EVERY offset in this row is in printed DOTS, the unit the whole read
side speaks and the unit the schema's names have always claimed.  The
one conversion — dots to the CELLS a window pose's 2x2 takes — happens
where the sampler is called, in `measure_window`, through the read
side's own `anchor.shifted_points`.  This row owns no shifting function
of its own, deliberately: it had one until 2026-08-31, it forgot the
`/ cell_dots` the read side applies, and the field silently became a
field of cells that every consumer then read as dots.

Nothing here mints a certificate or touches a decoder: the fit only
moves where the colour lane samples, and the colour lane's own held-out
gate still adjudicates whether the corrected features are better.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ..data import (Certificate, FieldFitted, FieldPlaneFit, JobResult,
                    PlaneField, PlaneFieldTiers)
from ..descriptor import (
    FactKey,
    Job,
    KEY_LANE_POSES,
    KEY_PAGE_CERTS,
    PluginDescriptor,
    Subject,
)
from ..format.identity import (CMY_PLANE_ORDER, Family, FormatRow,
                               SiteGeometry)
from ..lib import plane_field
from ..lib.geometry import TILE_CELLS
from . import color_region
from . import color_region_anchor as anchor
from . import field_tiers

PLUGIN: str = "fields"
STAGE_FIELDS: str = "fields"
FIELD_COST: int = 180
RUNG_COST: int = 2
PRICES: tuple[tuple[str, int], ...] = ((STAGE_FIELDS, FIELD_COST),)

N_PLANES: int = 3
N_STATES: int = 8
# a fit needs the page to be addressed and reading: eight certificates is
# the "this page is decoding at all" floor, not a support floor — the
# support that matters is per-plane sites, below
MIN_CERTIFICATES: int = 8
MIN_SITES: int = 256
MIN_STATE_CELLS: int = 8
# a plane whose ink never moves the channel by this much of full scale is
# dead here (the M281's starved Y): refuse rather than fit noise
MIN_SEPARATION: float = 0.02
# The "has something to say" leg, carried from the v1 line's third
# adoption test (its measured sheet-I cliff, 0.25 dots) and enforced by
# the WRITER: a field below it is not published at all, so the read side
# keeps the standing {1,y} residual.  Until 2026-08-31 it was compared
# against a median the fitter measured in CELLS, so on a c3 page it
# really demanded 0.75 dots of registration and on a c2 page 0.50; it
# now asks for the 0.25 dots it says.
#
# It does NOT keep a PLANE-COMMON reading out of a per-plane cell, and
# the comment that used to claim it did was wrong twice over — on the
# mechanism and on the number.  Measured 2026-08-31 through
# `measure/h3_plane_fields.py`, at honest units: the clean colour sim
# fits 0.973 / 0.974 / 0.975 dots on C / M / Y, one field of the same
# spatial shape on all three planes — a pose-versus-ink bias, not
# per-plane registration — which clears this floor by nearly 4x and
# publishes.  It moves no certificate there, but the field has no
# business carrying a pose correction (the v1 line's pose-writer arm
# measured NEGATIVE: -5 certificates, +2.1 pp cell BER), so what to do
# about a plane-common reading is an OPEN RULING, not something this
# floor settles.
MIN_DELTA_DOTS: float = 0.25
MAX_RESIDUAL: float = 0.995
PROBE_DOTS: float = 0.5
OUTER_PASSES: int = 4

# Diag only.  The field is per TILE, and a real sheet has thousands of
# them; the viewer draws one arrow per block anyway, so the event carries
# the field block-pooled to at most this many blocks per axis.  Cost per
# event is therefore fixed at three planes x 24 x 24 x (2 float32 + 1
# bool) = 15,552 bytes of array, whatever the tile matrix is.
DIAG_GRID_MAX: int = 24

LaneSubject = tuple[str, int, int]


@dataclass(frozen=True)
class WindowSites:
    """The cells of one window whose three plane bits are all known.

    Deliberately carries no raster: a lane-page can own a hundred
    windows, and holding each one's filtered crop for the length of a
    fit would cost gigabytes on a real sheet.  Each measuring pass
    re-cuts one window's crop, uses it for all three planes, and drops
    it.
    """

    page_cells_yx: np.ndarray
    states: np.ndarray
    scan_points_yx: np.ndarray
    pose_linear: np.ndarray
    window: color_region.RegionWindow
    known_bits: np.ndarray
    partition: field_tiers.SitePartition


@dataclass(frozen=True)
class Measurement:
    """One pass over every window: where each plane sits, and how the
    reading moves when the sampler moves."""

    codes: np.ndarray
    states: np.ndarray
    centres: np.ndarray
    gradients: np.ndarray


def window_sites(row: FormatRow, geometry: SiteGeometry,
                 window: color_region.RegionWindow,
                 certificates: dict) -> WindowSites | None:
    """One window's known cells, already split between the three tiers.

    The split is the ATTRIBUTION LAW (:mod:`field_tiers`): payload cells
    of certified tiles are photometric evidence, and the format's own
    furniture is halved by site parity between the anchor and the blind
    tiers.  It is computed once, here, so no later pass can reach a site
    that belongs to another tier.
    """
    rows = color_region.build_window_rows(row, geometry, window,
                                          certificates, {})
    complete = np.flatnonzero(
        np.asarray(rows.known_component_mask, bool).all(axis=1))
    if not complete.size:
        return None
    cells = np.asarray(rows.page_cells_yx, np.int64)[complete]
    return WindowSites(
        page_cells_yx=cells,
        states=np.asarray(rows.states, np.int64)[complete],
        scan_points_yx=np.asarray(rows.scan_points_yx,
                                  np.float64)[complete],
        pose_linear=anchor.pose_linear(window.affine),
        window=window,
        known_bits=np.asarray(
            rows.known_component_bits, np.uint8)[complete],
        partition=field_tiers.partition_sites(
            np.asarray(rows.furniture_kind, np.int64)[complete],
            np.ones(complete.size, bool), cells))


def window_crop(site: WindowSites, planes: anchor.Planes, pitch_px: float,
                divisor: float) -> tuple[int, int, np.ndarray] | None:
    y0, x0, raw = anchor.native_crop(
        planes,
        anchor.window_points(site.window.shape_yx_cells,
                             site.window.affine),
        anchor.window_halo(pitch_px))
    if raw.size == 0:
        return None
    return y0, x0, anchor.filtered_rgb(raw, pitch_px, divisor)


def state_levels(states: np.ndarray, values: np.ndarray,
                 min_cells: int = MIN_STATE_CELLS,
                 ) -> tuple[np.ndarray, np.ndarray]:
    """Median sampled value per (state, channel), and which states hold.

    The expected value of a cell depends on all three planes' ink, so the
    prediction is a per-state level table read off the page's own
    complete cells — no channel model, no oracle.
    """
    levels = np.zeros((N_STATES, N_PLANES), np.float64)
    live = np.zeros(N_STATES, bool)
    for state in range(N_STATES):
        selected = states == state
        if int(np.count_nonzero(selected)) < min_cells:
            continue
        levels[state] = np.median(values[selected], axis=0)
        live[state] = True
    return levels, live


def measure_window(site: WindowSites, crop: tuple[int, int, np.ndarray],
                   standing: tuple[np.ndarray | None, ...],
                   cell_dots: int,
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Sample the PHOTOMETRIC tier's cells at their standing offset.

    Only this tier's own rows are read (the attribution law: the
    furniture belongs to the anchor and blind tiers), and the per-state
    level table downstream is built from these cells alone, so no site
    informs two tiers even through a shared prediction.

    Every offset here is in printed DOTS, and reaches the raster through
    `anchor.shifted_points` — the one function that moves a sample point
    — which takes CELLS, so `cell_dots` divides on the way in.  That
    division is what makes the returned gradient a value per DOT, and
    therefore what makes the delta the solve hands back a delta in dots,
    the unit the whole read side already speaks.
    """
    y0, x0, filtered = crop
    rows = site.partition.photometric
    cells = site.page_cells_yx[rows]
    points = site.scan_points_yx[rows]
    n_rows = int(rows.size)
    centres = np.empty((n_rows, N_PLANES), np.float64)
    gradients = np.empty((n_rows, N_PLANES, 2), np.float64)

    def sample(offset_dots_xy: np.ndarray, plane: int) -> np.ndarray:
        return anchor.sample_rgb(
            filtered, y0, x0,
            anchor.shifted_points(points, site.pose_linear,
                                  offset_dots_xy / cell_dots))[:, plane]

    for plane in range(N_PLANES):
        field = standing[plane]
        offset = (np.zeros((n_rows, 2), np.float64) if field is None
                  else plane_field.evaluate(field, cells, TILE_CELLS))
        centres[:, plane] = sample(offset, plane)
        for axis in (0, 1):
            probe = np.zeros((n_rows, 2), np.float64)
            probe[:, axis] = PROBE_DOTS
            plus = sample(offset + probe, plane)
            minus = sample(offset - probe, plane)
            gradients[:, plane, axis] = (plus - minus) / (2.0 * PROBE_DOTS)
    return centres, gradients


def measure_pass(sites: tuple[WindowSites, ...], planes: anchor.Planes,
                 pitch_px: float, divisor: float,
                 standing: tuple[np.ndarray | None, ...],
                 tiles_yx: tuple[int, int],
                 cell_dots: int) -> Measurement | None:
    codes: list[np.ndarray] = []
    states: list[np.ndarray] = []
    centres: list[np.ndarray] = []
    gradients: list[np.ndarray] = []
    for site in sites:
        crop = window_crop(site, planes, pitch_px, divisor)
        if crop is None:
            continue
        rows = site.partition.photometric
        if not rows.size:
            continue
        window_centres, window_gradients = measure_window(site, crop,
                                                          standing,
                                                          cell_dots)
        codes.append(plane_field.tile_codes(site.page_cells_yx[rows],
                                            tiles_yx, TILE_CELLS))
        states.append(site.states[rows])
        centres.append(window_centres)
        gradients.append(window_gradients)
    if not codes:
        return None
    return Measurement(codes=np.concatenate(codes),
                       states=np.concatenate(states),
                       centres=np.concatenate(centres),
                       gradients=np.concatenate(gradients))


def plane_step(measurement: Measurement, levels: np.ndarray,
               live_states: np.ndarray, plane: int,
               tiles_yx: tuple[int, int],
               ) -> tuple[plane_field.NormalEquations, int] | None:
    """One plane's PHOTOMETRIC normal equations from one measuring pass."""
    separation = float(levels[live_states, plane].max()
                       - levels[live_states, plane].min())
    if separation < MIN_SEPARATION:
        return None
    keep = live_states[measurement.states]
    if not np.any(keep):
        return None
    states = measurement.states[keep]
    residual = ((levels[states, plane] - measurement.centres[keep, plane])
                / separation)
    gradient = measurement.gradients[keep, plane, :] / separation
    return (plane_field.accumulate(measurement.codes[keep], gradient,
                                   residual, tiles_yx),
            int(states.size))


def _tile_sampler(site: WindowSites, crop, rows: np.ndarray, plane: int,
                  cell_dots: int):
    """Sample one plane at some of a window's cells, displaced in DOTS.

    The same `anchor.shifted_points` the photometric pass uses, and the
    same `/ cell_dots` on the way in, so every tier speaks the one unit.
    """
    y0, x0, filtered = crop
    points = site.scan_points_yx[rows]

    def sample(offsets_dots_xy: np.ndarray) -> np.ndarray:
        offsets = np.atleast_2d(np.asarray(offsets_dots_xy, np.float64))
        if offsets.shape[0] == 1:
            moved = anchor.shifted_points(
                points, site.pose_linear,
                np.repeat(offsets, points.shape[0], axis=0) / cell_dots)
            return anchor.sample_rgb(filtered, y0, x0, moved)[:, plane]
        delta = (offsets[:, ::-1] / float(cell_dots)) @ site.pose_linear.T
        moved = points[None, :, :] + delta[:, None, :]
        values = anchor.sample_rgb(
            filtered, y0, x0, moved.reshape(-1, 2))[:, plane]
        return values.reshape(offsets.shape[0], points.shape[0])

    return sample


def anchor_pass(sites: tuple[WindowSites, ...], planes: anchor.Planes,
                pitch_px: float, divisor: float,
                tiles_yx: tuple[int, int], cell_dots: int,
                ) -> tuple[tuple[field_tiers.AnchorObservation, ...], ...]:
    """Correlate each plane against the format's own sites, per tile.

    The measurement is absolute — where this plane's ink is against where
    the format says it should be — so it is taken ONCE, at the committed
    pose, and reused by every outer pass.  Re-measuring it at the standing
    field would make the template follow the very correction being fitted,
    which is the circularity the phase-1 bias check measured at gain zero
    (measure/ysampler/README.md).
    """
    found: list[list[field_tiers.AnchorObservation]] = [
        [] for _ in range(N_PLANES)]
    for site in sites:
        rows_all = site.partition.anchor
        if not rows_all.size:
            continue
        crop = window_crop(site, planes, pitch_px, divisor)
        if crop is None:
            continue
        codes = plane_field.tile_codes(site.page_cells_yx[rows_all],
                                       tiles_yx, TILE_CELLS)
        for code in np.unique(codes):
            rows = rows_all[np.flatnonzero(codes == code)]
            if rows.size < field_tiers.ANCHOR_MIN_SITES:
                continue
            for plane in range(N_PLANES):
                radius = field_tiers.ANCHOR_RADIUS_DOTS[plane]
                measured = field_tiers.anchor_offsets(
                    _tile_sampler(site, crop, rows, plane, cell_dots),
                    site.known_bits[rows, plane],
                    np.ones(rows.size, np.float64), radius)
                if measured is None:
                    continue
                delta, quality = measured
                found[plane].append(field_tiers.AnchorObservation(
                    tile_code=int(code), delta_dots_xy=delta,
                    quality=float(quality), n_sites=int(rows.size),
                    saturated=field_tiers.saturated(delta, radius)))
    return tuple(tuple(rows) for rows in found)


def blind_pass(sites: tuple[WindowSites, ...], planes: anchor.Planes,
               pitch_px: float, divisor: float,
               tiles_yx: tuple[int, int], cell_dots: int,
               ) -> tuple[tuple[field_tiers.AnchorObservation, ...], ...]:
    """Pick each window's sampling offset blind, on its own labels.

    `measure/yask`'s A1 estimator, ported: sweep the offset, score each by
    the held-out log loss of a monotone map on the plane's own known
    labels, keep the best.  It asks only whether the READING improves, so
    it works where a gradient is flat and a correlation is weak — the
    dead-band regime — and it never sees a cell the anchor tier used.
    """
    found: list[list[field_tiers.AnchorObservation]] = [
        [] for _ in range(N_PLANES)]
    for site in sites:
        rows = site.partition.blind
        if rows.size < 2 * field_tiers.BLIND_MIN_PER_HALF:
            continue
        crop = window_crop(site, planes, pitch_px, divisor)
        if crop is None:
            continue
        cells = site.page_cells_yx[rows]
        codes = np.unique(plane_field.tile_codes(cells, tiles_yx,
                                                 TILE_CELLS))
        split = field_tiers.split_key(cells)
        for plane in range(N_PLANES):
            radius = field_tiers.ANCHOR_RADIUS_DOTS[plane]
            measured = field_tiers.blind_offset(
                _tile_sampler(site, crop, rows, plane, cell_dots),
                site.known_bits[rows, plane], split, radius)
            if measured is None:
                continue
            delta, weight = measured
            if weight <= 0.0:
                continue
            share = weight / float(codes.size)
            for code in codes:
                found[plane].append(field_tiers.AnchorObservation(
                    tile_code=int(code), delta_dots_xy=delta,
                    quality=float(share), n_sites=int(rows.size),
                    saturated=field_tiers.saturated(delta, radius)))
    return tuple(tuple(rows) for rows in found)


def relative_equations(observations, standing: np.ndarray | None,
                       tiles_yx: tuple[int, int], gain: float,
                       min_quality: float,
                       ) -> plane_field.NormalEquations:
    """An absolute measurement, expressed as a STEP on the standing field.

    The photometric tier fits a correction to where the sampler already
    points; the anchor and blind tiers say where the ink is, full stop.
    Subtracting the standing field at each tile puts all three in the same
    currency, so one solve serves them and the outer iteration stays
    exact.

    ``min_quality`` is passed EXPLICITLY by the caller, per tier, because
    the two tiers weigh themselves in different quantities — a
    correlation coefficient and a log-loss improvement — and an earlier
    version inferred the floor from ``gain`` instead.  That inference
    survived a merge while the branch it depended on did not, and the
    blind tier went silently unweighted again.  A floor that travels with
    its tier cannot be lost that way.
    """
    equations = field_tiers.anchor_equations(observations, tiles_yx,
                                             gain=gain,
                                             min_quality=min_quality)
    if standing is None:
        return equations
    return plane_field.NormalEquations(
        a=equations.a,
        b=equations.b - np.einsum("...ij,...j->...i", equations.a,
                                  np.asarray(standing, np.float64)),
        mass=equations.mass, total_square=equations.total_square)


def plane_relative(fields_by_plane: list) -> list:
    """Take the PLANE-COMMON part out of every plane's field.

    `PlaneField` is defined as a per-plane delta relative to the
    committed, plane-COMMON window pose.  A component all three planes
    share is by definition not that: it is a pose-versus-ink bias, and
    the field has no business carrying a pose correction — the v1 line's
    pose-writer arm measured NEGATIVE (−5 certificates, +2.1 pp cell
    BER), and the clean colour sim shows the bias directly at ~1 dot on
    all three planes with the same spatial shape.

    The common part is the MEDIAN across the three planes, not the mean
    of the other two.  Both cancel a common bias exactly
    (`median(b, b, b) = b`), but the mean-of-others REDISTRIBUTES one
    plane's real displacement onto its neighbours: with truth
    `(0, 0, D)` it returns `(−D/2, −D/2, D)`, measured on the displaced
    sim at C/M 0.45–0.56 against Y 1.117.  The median returns
    `(0, 0, D)`.
    """
    if any(field is None for field in fields_by_plane):
        return list(fields_by_plane)
    common = np.median(np.stack(fields_by_plane), axis=0)
    return [field - common for field in fields_by_plane]


def settle(fields_by_plane: list) -> list:
    """THE ORDER: take the common part out, THEN clamp.

    `MAX_DELTA_DOTS` bounds a PUBLISHED per-plane delta, and with honest
    units it binds (the displaced sim fits a median 1.598 against a 2.0
    ceiling).  Clamping first would bound a quantity that still carries
    the pose bias the field is about to discard — the wrong quantity —
    and, because the clamp is non-linear and per-plane, it would break
    the exact cancellation the median subtraction depends on: three
    planes clipped by different amounts no longer share a common part to
    remove.  Subtracting first leaves the clamp acting on exactly what
    gets written.  Measured, not argued: see the ORDER row in
    measure/ysampler/README.md.
    """
    return [None if field is None else plane_field.clamp(field)
            for field in plane_relative(fields_by_plane)]


def fit_page(sites: tuple[WindowSites, ...], planes: anchor.Planes,
             pitch_px: float, divisor: float, tiles_yx: tuple[int, int],
             cell_dots: int, passes: int = OUTER_PASSES,
             ) -> tuple[plane_field.FieldFit | None, ...]:
    """Iterated local least squares over the whole lane-page.

    THREE TIERS, ONE FIT.  Photometry is re-measured each pass, because
    it linearises about wherever the sampler now points; the anchor and
    blind tiers are measured ONCE at the committed pose, because what
    they measure is absolute and re-measuring it at the standing field
    would make their evidence follow the correction.  Their equations are
    re-expressed as a step on the standing field each pass, so all three
    are solved together, in printed dots, with each tier's contribution
    reported and each tier's effect measured by leaving it out.
    """
    standing: list[np.ndarray | None] = [None] * N_PLANES
    support: list[np.ndarray | None] = [None] * N_PLANES
    residual: list[float] = [1.0] * N_PLANES
    counted: list[int] = [0] * N_PLANES
    accounting: list[dict] = [{} for _ in range(N_PLANES)]
    checks: list[dict] = [{} for _ in range(N_PLANES)]
    anchors = anchor_pass(sites, planes, pitch_px, divisor, tiles_yx,
                          cell_dots)
    blinds = blind_pass(sites, planes, pitch_px, divisor, tiles_yx,
                        cell_dots)
    for _ in range(max(1, int(passes))):
        measurement = measure_pass(sites, planes, pitch_px, divisor,
                                   tuple(standing), tiles_yx, cell_dots)
        levels, live_states = (
            state_levels(measurement.states, measurement.centres)
            if measurement is not None
            else (np.zeros((N_STATES, N_PLANES)), np.zeros(N_STATES, bool)))
        raw: list[np.ndarray | None] = list(standing)
        for plane in range(N_PLANES):
            tiers: dict[str, plane_field.NormalEquations] = {}
            n_sites = 0
            if measurement is not None and np.any(live_states):
                photometric = plane_step(measurement, levels, live_states,
                                         plane, tiles_yx)
                if photometric is not None:
                    tiers[field_tiers.TIER_PHOTOMETRIC] = photometric[0]
                    n_sites += photometric[1]
            for name, observations, gain, floor in (
                    (field_tiers.TIER_ANCHOR, anchors[plane],
                     field_tiers.ANCHOR_GAIN,
                     field_tiers.ANCHOR_MIN_QUALITY),
                    (field_tiers.TIER_BLIND, blinds[plane], 1.0,
                     field_tiers.BLIND_MIN_WEIGHT)):
                if not observations:
                    continue
                equations = relative_equations(
                    observations, standing[plane], tiles_yx, gain, floor)
                if float(equations.mass.sum()) <= 0.0:
                    continue
                tiers[name] = equations
                n_sites += sum(o.n_sites for o in observations)
            check = field_tiers.gain_check(tiers)
            if check.get("refused"):
                if tiers.pop(field_tiers.TIER_ANCHOR, None) is not None:
                    n_sites -= sum(o.n_sites for o in anchors[plane])
            if not tiers:
                continue
            joint = plane_field.combine(*tiers.values())
            step, mass = plane_field.solve(joint)
            raw[plane] = (step if standing[plane] is None
                          else standing[plane] + step)
            support[plane] = mass
            residual[plane] = plane_field.fit_residual(joint, step)
            counted[plane] = n_sites
            accounting[plane] = field_tiers.leave_one_out(
                tiers, plane_field.solve)
            checks[plane] = check
        standing = settle(raw)
    return tuple(
        None if standing[plane] is None or support[plane] is None
        else plane_field.FieldFit(
            delta_dots_xy=standing[plane], support=support[plane],
            residual=residual[plane],
            median_delta_dots=plane_field.median_magnitude_dots(
                standing[plane], support[plane]),
            n_sites=counted[plane], tiers=accounting[plane],
            gain_check=checks[plane])
        for plane in range(N_PLANES))


def publishable(fit: plane_field.FieldFit) -> bool:
    return (fit.n_sites >= MIN_SITES
            and fit.median_delta_dots >= MIN_DELTA_DOTS
            and fit.residual <= MAX_RESIDUAL)


def refusal(fit: plane_field.FieldFit) -> str:
    """Why `publishable` said no — "" exactly when it said yes.

    Reporting only: every failing leg with its own numbers, so a viewer
    can name WHICH floor refused a real measurement.  Each leg is the
    NEGATION of the decision's own comparison rather than its mirror
    image, so a non-comparable value (a NaN out of a degenerate solve)
    refuses in both places instead of failing the decision and passing
    the explanation.
    """
    if publishable(fit):
        return ""
    legs = []
    if not fit.n_sites >= MIN_SITES:
        legs.append(f"sites {fit.n_sites}<{MIN_SITES}")
    if not fit.median_delta_dots >= MIN_DELTA_DOTS:
        legs.append(f"median {fit.median_delta_dots:.2f}d"
                    f"<{MIN_DELTA_DOTS:.2f}d")
    if not fit.residual <= MAX_RESIDUAL:
        legs.append(f"residual {fit.residual:.3f}>{MAX_RESIDUAL:.3f}")
    return " · ".join(legs)


def block_size(n_tiles: int, cap: int = DIAG_GRID_MAX) -> int:
    """Tiles per diag block: the smallest that keeps the grid within
    `cap` on this axis."""
    return max(1, -(-max(1, int(n_tiles)) // max(1, int(cap))))


def pool_field(delta_dots_xy: np.ndarray, support: np.ndarray,
               block_yx: tuple[int, int],
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Block-pool one plane's tile field for the diag event.

    Returns the pooled delta VECTOR (gy, gx, 2), the pooled |delta|
    MAGNITUDE (gy, gx), and the has-data flag.  Both poolings average
    over the block's tiles that CARRY EVIDENCE, and a block with none of
    those is flagged rather than averaged to zero — the pane paints
    those as blind spots, and a blind spot averaged into a delta would
    read as a measurement.

    The magnitude is pooled in its own right because `hypot` of the
    pooled vector is a different number: opposing deltas inside one
    block cancel toward zero there while every tile of it may clear the
    publish floor.  The band shades on the magnitude, so its shading and
    `publishable` — a floor on the median per-tile magnitude — answer
    the same question; the vector keeps its own job, which is the arrow's
    direction.
    """
    delta = np.asarray(delta_dots_xy, np.float64)
    live = np.asarray(support, np.float64) > 0.0
    tiles_y, tiles_x = live.shape
    block_y, block_x = (max(1, int(v)) for v in block_yx)
    rows = np.arange(tiles_y) // block_y
    columns = np.arange(tiles_x) // block_x
    grid_y, grid_x = int(rows[-1]) + 1, int(columns[-1]) + 1
    code = (rows[:, None] * grid_x + columns[None, :]).ravel()
    weight = np.bincount(code, weights=live.ravel().astype(np.float64),
                         minlength=grid_y * grid_x)
    grid = np.zeros((grid_y, grid_x, 2), np.float32)
    for axis in (0, 1):
        total = np.bincount(code,
                            weights=(delta[..., axis] * live).ravel(),
                            minlength=grid_y * grid_x)
        grid[..., axis] = (total
                           / np.maximum(weight, 1.0)).reshape(grid_y, grid_x)
    magnitude = np.bincount(
        code, weights=(np.hypot(delta[..., 0], delta[..., 1]) * live).ravel(),
        minlength=grid_y * grid_x)
    return (grid,
            (magnitude / np.maximum(weight, 1.0)
             ).reshape(grid_y, grid_x).astype(np.float32),
            (weight > 0.0).reshape(grid_y, grid_x))


def plane_row(plane: int, fit: plane_field.FieldFit | None,
              block_yx: tuple[int, int]) -> FieldPlaneFit:
    name = CMY_PLANE_ORDER[plane]
    if fit is None:
        return FieldPlaneFit(
            plane=plane, plane_name=name, published=False,
            refusal="no fit — plane dead here, or no live states",
            median_delta_dots=None, n_sites=None, residual=None,
            support_tiles=None, delta_grid_dots_xy=None,
            magnitude_grid_dots=None, has_data=None)
    grid, magnitude, has_data = pool_field(
        fit.delta_dots_xy, fit.support, block_yx)
    why = refusal(fit)
    return FieldPlaneFit(
        plane=plane, plane_name=name, published=(why == ""), refusal=why,
        median_delta_dots=float(fit.median_delta_dots),
        n_sites=int(fit.n_sites), residual=float(fit.residual),
        support_tiles=int(np.count_nonzero(
            np.asarray(fit.support, np.float64) > 0.0)),
        delta_grid_dots_xy=grid, magnitude_grid_dots=magnitude,
        has_data=has_data)


def diag_event(tiles_yx: tuple[int, int],
               fits: tuple[plane_field.FieldFit | None, ...],
               capture_id: str, level_index: int, page: int,
               n_certificates: int) -> FieldFitted:
    """The one diag event a fit emits — every plane, published or not."""
    block_yx = (block_size(tiles_yx[0]), block_size(tiles_yx[1]))
    return FieldFitted(
        capture=capture_id, level_index=level_index, page=page,
        n_certificates=n_certificates, tiles_yx=tuple(int(v)
                                                     for v in tiles_yx),
        block_tiles_yx=block_yx, publish_floor_dots=MIN_DELTA_DOTS,
        planes=tuple(plane_row(plane, fit, block_yx)
                     for plane, fit in enumerate(fits)))


def fit_job(row: FormatRow, geometry: SiteGeometry,
            windows: tuple[color_region.RegionWindow, ...],
            plane_rasters: tuple, certificates: dict, capture_id: str,
            level_index: int, page: int, n_certificates: int) -> JobResult:
    started = time.thread_time()
    planes: anchor.Planes = (plane_rasters[0].open(),
                             plane_rasters[1].open(),
                             plane_rasters[2].open())
    ordered = tuple(sorted(windows,
                           key=lambda window: window.patch_ordinal))
    pitch_px = float(np.median([window.pitch_px for window in ordered]))
    halo = anchor.window_halo(pitch_px)
    divisor = anchor.native_divisor(tuple(
        anchor.crop_maximum(
            planes,
            anchor.window_points(window.shape_yx_cells, window.affine),
            halo)
        for window in ordered))
    sites = tuple(
        site for site in (
            window_sites(row, geometry, window, certificates)
            for window in ordered)
        if site is not None)
    if not sites:
        return JobResult((), (), time.thread_time() - started)
    fits = fit_page(sites, planes, pitch_px, divisor, row.tiles_yx,
                    color_region.cell_dots_of(row))
    facts: list[object] = []
    events: list[object] = []
    for plane, fit in enumerate(fits):
        if fit is not None:
            events.append(PlaneFieldTiers(
                capture_id=capture_id, level_index=level_index, page=page,
                plane=plane, tiers=fit.tiers, gain_check=fit.gain_check,
                n_sites=fit.n_sites,
                median_delta_dots=fit.median_delta_dots))
        if fit is None or not publishable(fit):
            continue
        facts.append(PlaneField(
            capture_id=capture_id, level_index=level_index, page=page,
            plane=plane, delta_dots_xy=fit.delta_dots_xy,
            support=fit.support, n_certificates=n_certificates,
            n_sites=fit.n_sites, residual=fit.residual,
            median_delta_dots=fit.median_delta_dots))
    # The event is the WHOLE fit, refused planes included; the facts
    # above are only the part the writer's floors let through.
    events.append(diag_event(row.tiles_yx, fits, capture_id, level_index,
                             page, n_certificates))
    return JobResult(tuple(facts), tuple(events),
                     time.thread_time() - started)


def page_certificate_count(store: object, page: int) -> int:
    return sum(1 for key in store.certificate_keys() if key[0] == page)


def prepare_fields(store: object, subject: Subject,
                   stage: str) -> Job | None:
    capture_id, level_index, page = subject
    if not store.plane_fields_enabled():
        return None
    wids = store.lane_page_windows(capture_id, level_index, page)
    if not wids:
        return None
    n_certificates = page_certificate_count(store, page)
    if n_certificates < MIN_CERTIFICATES:
        return None
    windows = tuple(color_region.region_window(store, wid) for wid in wids)
    plane_rasters = store.rgb_planes((capture_id, level_index))
    certificates = store.certificates()
    row = store.row
    site_geometry = store.geometry

    def job() -> JobResult:
        return fit_job(row, site_geometry, windows, plane_rasters,
                       certificates, capture_id, level_index, page,
                       n_certificates)

    return job


def _fields_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    if store.row.family is Family.K or not store.plane_fields_enabled():
        return ()
    return tuple(
        (capture_id, level_index, fact.page)
        for capture_id, level_index in sorted(
            store.lanes_on_page(fact.page)))


def _fields_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    return ((KEY_PAGE_CERTS, subject[2]),
            (KEY_LANE_POSES,) + tuple(subject))


def _fields_eligible(store: object, subject: Subject) -> bool:
    capture_id, level_index, page = subject
    return bool(store.lane_page_windows(capture_id, level_index, page))


def _fields_retire(store: object, subject: Subject) -> bool:
    return bool(store.done_grid(subject[2]).all())


def _fields_stage(store: object, subject: Subject) -> str | None:
    return STAGE_FIELDS


def _fields_cost(store: object, subject: Subject, stage: str,
                 attempts: int, last_cost: int) -> int:
    return FIELD_COST * attempts + RUNG_COST * subject[1]


FIELDS_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN,
    subject_kind="lane",
    born_by=(Certificate,),
    subjects_of=_fields_subjects,
    reads=_fields_reads,
    eligible=_fields_eligible,
    stage=_fields_stage,
    cost=_fields_cost,
    retire=_fields_retire,
    prepare=prepare_fields,
    produces=(PlaneField,),
    prices=PRICES,
)

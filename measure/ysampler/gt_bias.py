"""PHASE 1 -- the bias check: are ink-free Y anchors measuring the sheet?

    PYTHONPATH=. <checkout>/env314t/bin/python \
        -m measure.ysampler.gt_bias --out scratch/ysampler/gt-bias.json

The question, in one line: the §15.6 repair gave the Y plane a dense
word-site anchor lattice it never had -- does that lattice measure the
REAL per-plane registration, and on what scale?

WHY THIS FOOTING.  The lattice is a property of a printed sheet, so the
answer has to come off one.  Sheet I is the only printed page carrying
both halves of a registration ground truth (:mod:`_sheet_i`): the e033
GT-correlation tool's per-tile plane displacements, and the plane-fields
swim pilot's decode-optimal offsets.  Neither is re-derived here.

WHY NO DECODE.  The anchor kernel needs a pose, the format's furniture
truth, and pixels -- not a receiver state.  The GT tool's own page
affine plus its own per-patch plane-COMMON lock supply the pose, the
format supplies the furniture, and the capture is a memmap read one tile
at a time.  That is the `measure/yask` lesson ("bringing the poses is
also the better evidence") applied to a page whose GT already carries
the lock.  Peak resident stays around a gigabyte and the whole pass is
minutes; nothing is decoded and no state is opened.

WHAT IS COMPARED.  Everything is made PLANE-RELATIVE before it is
compared -- ``Y - (C + M) / 2`` -- which is the GT file's own
``dY_rel_x`` and which cancels the page affine's error, the paper's
pose, and the scanner's common warp out of both sides at once.  Three
estimators are measured on the identical tiles:

* ANCHOR -- holo3's own ``rectified_ncc`` on 3x3 known/blind blocks,
  with the ink-free centre (the §15.6 variant) and the per-plane search
  radius (project-lead ruling: Y at +-2.2 dots, C and M untouched).
* PHOTOMETRIC -- holo3's own ``plane_field`` normal equations, built the
  way ``plugins/fields.py`` builds them, on the same cells.
* GT -- recorded, not measured here.

and the swim pilot's decode-optimal offsets give the third leg: what a
DECODER wanted at ten of those tiles.

WHAT IT REPORTS.  Shape agreement (Pearson, Spearman, sign agreement)
against the recorded sinusoid, per-plane GAIN (the slope of estimator on
truth, and of anchor on photometric -- the number a joint fit needs to
put the two tiers on one scale), and the STABILITY of that gain across
tile rows, bands and bootstrap resamples.  It reports a verdict; it does
not adopt anything.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import _sheet_i

PLANE_NAMES = _sheet_i.PLANE_NAMES
N_PLANES = 3
PLANE_Y = 2
# The ruled per-plane search radius, in printed dots.  A plane absent
# from this table keeps production's own radius, unevaluated.
RADIUS_DOTS_BY_PLANE: dict[int, float] = {PLANE_Y: 2.2}
# Anchor populations, by the known bit at the centre.  Production only
# ever samples INK; FREE is the §15.6 variant and the only population Y
# has at a word site, because the colour word renders states {0, 3}.
POPULATION_INK = "ink"
POPULATION_FREE = "free"
POPULATION_FURNITURE = "furniture"
POPULATION_SPARSE = "sparse"
KIND_WORD = 0
KIND_DUST = 1
# A tile whose plane-common lock did not correlate is not a measurement.
MIN_COMMON_CORR = 0.4
MIN_ANCHORS_PER_TILE = 6
# The photometric probe, in the unit the fitter's own arithmetic uses
# (see `probe_cells` below -- this instrument states the unit rather
# than inheriting a name).
PROBE_CELLS = 0.5
MIN_STATE_CELLS = 8
N_STATES = 8


# --------------------------------------------------------------------
# one tile
# --------------------------------------------------------------------

@dataclass
class TileMeasurement:
    tile_y: int
    tile_x: int
    anchor_dx_dots: dict[tuple[int, str], float] = field(default_factory=dict)
    anchor_n: dict[tuple[int, str], int] = field(default_factory=dict)
    anchor_quality: dict[tuple[int, str], float] = field(
        default_factory=dict)
    anchor_saturation: dict[tuple[int, str], float] = field(
        default_factory=dict)


@dataclass(frozen=True)
class TileContext:
    """Everything about a tile that a sampling PROBE must not move.

    The two estimators both carry a self-referential part, and a probe
    that moves it measures nothing:

    * the anchor's 3x3 template is 1 known cell and 8 BLIND cells, read
      at a pose.  Move the pose and the blind reading follows, so the
      template moves with the frame and the correlation sees no
      displacement at all.  In production that pose is the plane-COMMON
      one, and what the anchor then measures is the PER-PLANE residual --
      exactly the quantity a per-plane field wants.  A calibration has to
      reproduce that: template frozen at the common pose, frame moved.
    * the photometric prediction is a per-state level table read off the
      page's own cells.  Shift every cell on the page and the level table
      shifts with them, absorbing the probe exactly.  Freeze the table.

    Both freezes are taken once, at the unshifted frame, and reused.
    """

    tile: object
    page_cells: np.ndarray
    states: np.ndarray
    kinds: np.ndarray
    known_bits: np.ndarray
    furniture: np.ndarray
    detected: np.ndarray
    confident: np.ndarray
    pitch_px: float
    divisor: float


def _tile_cells() -> np.ndarray:
    grid = np.stack(np.meshgrid(
        np.arange(_sheet_i.TILE_DOTS // _sheet_i.CELL_DOTS),
        np.arange(_sheet_i.TILE_DOTS // _sheet_i.CELL_DOTS),
        indexing="ij"), axis=-1)
    return grid.reshape(-1, 2).astype(np.int64)


def _pitch_px(affine) -> float:
    return float(np.hypot(affine[0], affine[3]))


def _local_affine(affine, y0: int, x0: int):
    return (affine[0], affine[1], affine[2] - y0,
            affine[3], affine[4], affine[5] - x0)


def context_tile_y(tile) -> int:
    return int(tile.tile_y)


def context_tile_x(tile) -> int:
    return int(tile.tile_x)


def assert_cells_are_solid(truth_dots, tile) -> None:
    """A cell is a solid block of dots, so one dot names the cell."""
    y0 = context_tile_y(tile) * _sheet_i.TILE_DOTS
    x0 = context_tile_x(tile) * _sheet_i.TILE_DOTS
    byte0, byte1 = x0 // 8, (x0 + _sheet_i.TILE_DOTS + 7) // 8
    raw = np.ascontiguousarray(
        truth_dots[:, y0:y0 + _sheet_i.TILE_DOTS, byte0:byte1])
    bits = np.unpackbits(raw, axis=2, bitorder="big")
    dots = bits[:, :, x0 - byte0 * 8:x0 - byte0 * 8 + _sheet_i.TILE_DOTS]
    step = _sheet_i.CELL_DOTS
    for dy in range(step):
        for dx in range(step):
            if not np.array_equal(dots[:, dy::step, dx::step],
                                  dots[:, ::step, ::step]):
                raise AssertionError(
                    "the emitted field is not solid within a cell: the "
                    "oracle template cannot be read off one dot")


def _tile_crop(anchor, planes, tile, probe_dots_x: float):
    """One tile's raw crop and its crop-local affine, probe included.

    ``probe_dots_x`` moves the SAMPLING FRAME along page +x by that many
    printed dots; the sheet does not move, so the content appears
    displaced by the same amount with the opposite sign.
    """
    affine = _sheet_i.tile_affine(tile)
    if probe_dots_x:
        affine = (affine[0], affine[1],
                  affine[2] + probe_dots_x * _sheet_i.AY[1],
                  affine[3], affine[4],
                  affine[5] + probe_dots_x * _sheet_i.AX[1])
    pitch_px = _pitch_px(affine)
    shape_cells = (_sheet_i.TILE_DOTS // _sheet_i.CELL_DOTS,) * 2
    points = anchor.window_points(shape_cells, affine)
    y0, x0, raw = anchor.native_crop(
        planes, points, anchor.window_halo(pitch_px))
    if raw.size == 0 or raw.shape[0] < 8 or raw.shape[1] < 8:
        return None
    return _local_affine(affine, y0, x0), raw, pitch_px


def tile_context(anchor, color_model, tile_codec, row, geometry, planes,
                 tile, local_cells, truth_dots=None) -> TileContext | None:
    """Freeze one tile's format truth and its blind reading at the pose.

    ``truth_dots``, when given, replaces the BLIND half of the template
    with the emitted cell field -- the ORACLE arm.  It stands in for the
    template a certified tile supplies and exists to answer one
    question: does the anchor need a template that is independent of the
    pose it is measuring?
    """
    cut = _tile_crop(anchor, planes, tile, 0.0)
    if cut is None:
        return None
    local, raw, pitch_px = cut
    origin = np.asarray(
        (tile.tile_y * _sheet_i.TILE_DOTS // _sheet_i.CELL_DOTS,
         tile.tile_x * _sheet_i.TILE_DOTS // _sheet_i.CELL_DOTS),
        np.int64)
    page_cells = local_cells + origin
    divisor = anchor.native_divisor((float(np.max(raw)),))
    filtered = anchor.filtered_rgb(raw, pitch_px, divisor)
    features = anchor.sample_rgb(
        filtered, 0, 0, anchor.pose_points(local, local_cells))

    states, kinds = color_model.reference_states(
        row, geometry, 0, page_cells)
    furniture = states >= 0
    known_bits = np.zeros((states.size, N_PLANES), np.uint8)
    known_bits[furniture] = tile_codec.states_to_planes(
        states[furniture].astype(np.uint8))

    detected = np.empty((states.size, N_PLANES), np.bool_)
    confident = np.empty((states.size, N_PLANES), np.bool_)
    for plane in range(N_PLANES):
        bits, llr = color_model.blind_component_bits(features[:, plane])
        detected[:, plane] = np.asarray(bits, bool)
        confident[:, plane] = (
            np.abs(llr) >= color_model.BLIND_CONFIDENT_LLR)
    detected[furniture] = known_bits[furniture].astype(bool)
    confident[furniture] = True
    if truth_dots is not None:
        cells = _sheet_i.truth_cell_bits(
            truth_dots, context_tile_y(tile), context_tile_x(tile))
        detected = cells.reshape(-1, N_PLANES).astype(bool)
        confident = np.ones_like(detected)
    return TileContext(
        tile=tile, page_cells=page_cells, states=states, kinds=kinds,
        known_bits=known_bits, furniture=furniture, detected=detected,
        confident=confident, pitch_px=pitch_px, divisor=divisor)


def measure_tile(anchor, planes, context: TileContext, local_cells,
                 neighbor_indices, radius_by_plane: dict[int, float],
                 probe_dots_x: float = 0.0, block_cells: int = 0):
    """One tile at one sampling frame: NCC anchors, and photometry.

    Everything self-referential comes from ``context``, frozen at the
    unprobed frame; only the sampling frame moves.
    """
    cut = _tile_crop(anchor, planes, context.tile, probe_dots_x)
    if cut is None:
        return None
    local, raw, _pitch = cut
    crop_planes = tuple(np.ascontiguousarray(raw[..., c])
                        for c in range(N_PLANES))
    filtered = anchor.filtered_rgb(raw, context.pitch_px, context.divisor)

    measurement = TileMeasurement(context.tile.tile_y, context.tile.tile_x)
    from holo3.plugins import field_tiers
    for plane in range(N_PLANES):
        measured = sparse_offset(
            anchor, field_tiers, filtered, local, local_cells, context,
            plane, _radius_dots(anchor, radius_by_plane.get(plane)),
            context.kinds)
        if measured is None:
            continue
        key = (plane, POPULATION_SPARSE)
        measurement.anchor_dx_dots[key] = float(measured[0][0])
        measurement.anchor_n[key] = 1
        measurement.anchor_quality[key] = float(measured[1])
        radius = _radius_dots(anchor, radius_by_plane.get(plane))
        measurement.anchor_saturation[key] = float(
            field_tiers.saturated(measured[0], radius))
    if block_cells:
        for plane in range(N_PLANES):
            measured = furniture_offset(
                anchor, crop_planes, local, context, plane,
                radius_by_plane.get(plane), block_cells)
            if measured is None:
                continue
            key = (plane, POPULATION_FURNITURE)
            measurement.anchor_dx_dots[key] = float(measured[0][0])
            measurement.anchor_n[key] = 1
            measurement.anchor_quality[key] = float(measured[1])
            radius = _radius_dots(anchor, radius_by_plane.get(plane))
            measurement.anchor_saturation[key] = float(
                max(abs(measured[0][0]), abs(measured[0][1]))
                >= radius - 0.26)
    word = context.furniture & (context.kinds == KIND_WORD)
    for plane in range(N_PLANES):
        for population, want in ((POPULATION_INK, 1), (POPULATION_FREE, 0)):
            rows = np.flatnonzero(
                word & (context.known_bits[:, plane] == want))
            if rows.size == 0:
                continue
            offsets, quality = _anchor_offsets(
                anchor, crop_planes, local, local_cells, neighbor_indices,
                rows, plane, context.detected, context.confident,
                radius_by_plane.get(plane))
            if offsets.shape[0] < MIN_ANCHORS_PER_TILE:
                continue
            key = (plane, population)
            weights = np.maximum(quality, 0.0)
            measurement.anchor_dx_dots[key] = float(
                _weighted_median(offsets[:, 0], weights))
            measurement.anchor_n[key] = int(offsets.shape[0])
            measurement.anchor_quality[key] = float(np.median(quality))
            radius = _radius_dots(anchor, radius_by_plane.get(plane))
            measurement.anchor_saturation[key] = float(np.mean(
                np.max(np.abs(offsets), axis=1) >= radius - 0.26))

    photometry = _photometry(anchor, filtered, local, local_cells,
                             context.states, context.furniture)
    return measurement, photometry


def _radius_dots(anchor, radius_dots: float | None) -> float:
    """What the rectification realizes for a requested radius, in dots.

    The search is a whole number of rectified pixels, so a request is a
    lower bound; the realized value is what saturation must be scored
    against.
    """
    px_per_dot = int(anchor.RECTIFIED_PX_PER_DOT)
    cell_px = px_per_dot * _sheet_i.CELL_DOTS
    if radius_dots is None:
        return max(2, round(anchor.ANCHOR_MAX_SHIFT_PX * cell_px / 6.0)) \
            / px_per_dot
    return max(2, int(np.ceil(radius_dots * px_per_dot - 1e-9))) / px_per_dot


def _anchor_offsets(anchor, crop_planes, affine, local_cells,
                    neighbor_indices, rows, plane, detected, confident,
                    radius_dots: float | None):
    """holo3's own NCC kernel, ink-free centre, per-plane radius.

    The forced ink centre ``bits[1, 1] = 1`` that ``measure_anchor``
    applies is simply not applied: the caller has already written the
    KNOWN bit at confidence 1.0 into ``detected``, which is what makes
    the forced line a no-op on the ink population and a polarity gate on
    every other one (§15.6).  Everything else -- block assembly, the
    weights, the quality floor -- is production's own.
    """
    constant = None
    if radius_dots is not None:
        px_per_dot = int(anchor.RECTIFIED_PX_PER_DOT)
        cell_px = px_per_dot * _sheet_i.CELL_DOTS
        wanted_px = max(2, int(np.ceil(radius_dots * px_per_dot - 1e-9)))
        constant = wanted_px * 6.0 / cell_px
    offsets: list[np.ndarray] = []
    quality: list[float] = []
    saved = anchor.ANCHOR_MAX_SHIFT_PX
    if constant is not None:
        anchor.ANCHOR_MAX_SHIFT_PX = constant
    try:
        for row_index in rows.tolist():
            indices = neighbor_indices[row_index]
            if np.any(indices < 0):
                continue
            bits = detected[indices, plane].reshape(3, 3).copy()
            weights = np.where(
                confident[indices, plane].reshape(3, 3), 1.0, 0.05)
            if bits.min() == bits.max():
                continue
            centre = local_cells[row_index]
            measured = anchor.rectified_ncc(
                crop_planes, affine, _sheet_i.CELL_DOTS,
                (int(centre[0]), int(centre[1])), bits, weights, plane)
            if measured is None or measured[1] < anchor.ANCHOR_MIN_Q:
                continue
            offsets.append(measured[0])
            quality.append(float(measured[1]))
    finally:
        anchor.ANCHOR_MAX_SHIFT_PX = saved
    if not offsets:
        return np.zeros((0, 2), np.float64), np.zeros(0, np.float64)
    return np.asarray(offsets, np.float64), np.asarray(quality, np.float64)


def furniture_offset(anchor, crop_planes, affine, context, plane,
                     radius_dots: float | None, block_cells: int):
    """One tile, one plane: NCC on the FORMAT'S OWN SITES alone.

    The 3x3 anchor cannot work on a payload-surrounded site, because
    eight of its nine cells are a blind reading taken at the very pose it
    is measuring (the oracle arm measures how much that costs: everything).
    The format's furniture is the way out -- 100 word sites and 20 dust
    sites per tile whose values the receiver knows before it reads
    anything.  They are scattered, so no 3x3 block is made of them; but
    ``rectified_ncc`` is general over template SHAPE, so the template can
    be the WHOLE TILE with weight 1.0 at the furniture and 0.0 everywhere
    else.  That is a blind, truth-independent template with ~120 known
    cells -- and it is the same object `measure/yask`'s A1 arm found by a
    different route ("the format's own dust sites, used as a registration
    anchor rather than as an address").
    """
    saved = anchor.ANCHOR_MAX_SHIFT_PX
    if radius_dots is not None:
        px_per_dot = int(anchor.RECTIFIED_PX_PER_DOT)
        cell_px = px_per_dot * _sheet_i.CELL_DOTS
        wanted_px = max(2, int(np.ceil(radius_dots * px_per_dot - 1e-9)))
        anchor.ANCHOR_MAX_SHIFT_PX = wanted_px * 6.0 / cell_px
    try:
        side = _sheet_i.TILE_DOTS // _sheet_i.CELL_DOTS
        known = context.furniture.reshape(side, side)
        bits = context.known_bits[:, plane].reshape(side, side)
        weights = known.astype(np.float64)
        if block_cells < side:
            lo = (side - block_cells) // 2
            bits = bits[lo:lo + block_cells, lo:lo + block_cells]
            weights = weights[lo:lo + block_cells, lo:lo + block_cells]
            centre = (lo + block_cells / 2.0, lo + block_cells / 2.0)
        else:
            centre = (side / 2.0, side / 2.0)
        live = bits[weights > 0.0]
        if live.size < 16 or live.min() == live.max():
            return None
        return anchor.rectified_ncc(
            crop_planes, affine, _sheet_i.CELL_DOTS, centre,
            bits.astype(np.uint8), weights, plane)
    finally:
        anchor.ANCHOR_MAX_SHIFT_PX = saved


def sparse_offset(anchor, field_tiers, filtered, affine, local_cells,
                  context, plane, radius_dots: float, kinds):
    """The PRODUCTION tier's own kernel, measured on the same tiles.

    ``holo3.plugins.field_tiers`` correlates a plane against the format's
    sites SPARSELY -- ~120 known cells rather than a tile's 4,096 pixels
    -- because the dense whole-tile NCC spends 34 times the work to use
    the same evidence (90 ms against 4 ms a tile at c3).  It is a
    different kernel from ``rectified_ncc``, so it gets its own
    calibration here rather than inheriting one.
    """
    # exactly the sites production gives this tier: the format's
    # furniture, halved by site parity (the attribution law).  Word sites
    # alone would refuse Y, which is the whole point of the parity split.
    partition = field_tiers.partition_sites(
        kinds, context.furniture, context.page_cells)
    rows = partition.anchor
    if rows.size < field_tiers.ANCHOR_MIN_SITES:
        return None
    cells = local_cells[rows].astype(np.float64)
    base = anchor.pose_points(affine, cells)
    linear = anchor.pose_linear(affine)

    def sample(grid: np.ndarray):
        delta_yx = (grid[:, ::-1] / _sheet_i.CELL_DOTS) @ linear.T
        points = base[None, :, :] + delta_yx[:, None, :]
        values = anchor.sample_rgb(
            filtered, 0, 0, points.reshape(-1, 2))[:, plane]
        return values.reshape(grid.shape[0], base.shape[0])

    bits = context.known_bits[rows, plane].astype(np.float64)
    weights = np.ones(rows.size, np.float64)
    return field_tiers.anchor_offsets(sample, bits, weights, radius_dots)


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    v = np.asarray(values)[order]
    w = np.asarray(weights)[order]
    total = float(w.sum())
    if total <= 0.0:
        return float(np.median(v))
    cumulative = np.cumsum(w) / total
    return float(v[int(np.searchsorted(cumulative, 0.5))])


def _photometry(anchor, filtered, affine, local_cells, states, furniture):
    """One tile's photometric evidence, in the fitter's own arithmetic.

    ``plugins/fields.py`` samples each plane at the standing offset and
    at four probes around it and turns the pair into
    ``v(delta) ~ v0 + g . delta``.  This reproduces that for the standing
    offset ZERO -- one measuring pass, which is what a bias check wants:
    an unconditioned reading of where each plane sits.

    UNITS, stated because the production module does not: the probe is
    applied through ``pose_linear``, which maps CELLS to pixels, so the
    gradient is per CELL and the delta the solve returns is in CELLS.
    This instrument keeps that unit and converts once, at the boundary,
    by ``* CELL_DOTS``.
    """
    rows = np.flatnonzero(furniture)
    if rows.size == 0:
        return None
    cells = local_cells[rows].astype(np.float64)
    linear = anchor.pose_linear(affine)
    base = anchor.pose_points(affine, cells)
    centres = anchor.sample_rgb(filtered, 0, 0, base)
    gradients = np.empty((rows.size, N_PLANES, 2), np.float64)
    for axis in (0, 1):
        probe = np.zeros((rows.size, 2), np.float64)
        probe[:, axis] = PROBE_CELLS
        delta_yx = probe[:, ::-1] @ linear.T
        plus = anchor.sample_rgb(filtered, 0, 0, base + delta_yx)
        minus = anchor.sample_rgb(filtered, 0, 0, base - delta_yx)
        gradients[:, :, axis] = (plus - minus) / (2.0 * PROBE_CELLS)
    return states[rows].astype(np.int64), centres, gradients


# --------------------------------------------------------------------
# the page-wide photometric solve
# --------------------------------------------------------------------

#: A per-tile solve is unridged, so a tile whose two normal directions
#: are not both informed must be refused rather than inverted.
MIN_INFORMATION = 1e-3


def state_levels(states: np.ndarray, centres: np.ndarray):
    """The per-state level table ``plugins/fields.py`` fits, page-wide."""
    levels = np.zeros((N_STATES, N_PLANES), np.float64)
    live = np.zeros(N_STATES, bool)
    for state in range(N_STATES):
        selected = states == state
        if int(np.count_nonzero(selected)) < MIN_STATE_CELLS:
            continue
        levels[state] = np.median(centres[selected], axis=0)
        live[state] = True
    return levels, live


def photometric_field(plane_field, photometry, frozen_levels=None):
    """The photometric delta per tile, per plane, in DOTS.

    Evidence is built exactly as ``plugins/fields.py`` builds it: a
    page-wide per-state level table, then per-tile CENTRED normal
    equations from the plane's own sampled value and its half-probe
    gradient.  The SOLVE here is deliberately not the production one --
    production pools a 2-tile Gaussian neighbourhood over a whole page
    and shrinks against a ridge, and both of those would put SHRINKAGE
    into a number this pass is trying to read as estimator GAIN.  One
    tile, one unridged 2x2 solve, and a refusal where the tile's own
    evidence does not inform both directions.

    UNITS: the gradient is per CELL (see ``_photometry``), so the solve
    returns cells and the conversion to dots happens once, here.
    """
    codes = np.concatenate([
        np.full(item[0].size, index, np.int64)
        for index, item in enumerate(photometry)])
    states = np.concatenate([item[0] for item in photometry])
    centres = np.concatenate([item[1] for item in photometry])
    gradients = np.concatenate([item[2] for item in photometry])

    if frozen_levels is None:
        levels, live = state_levels(states, centres)
    else:
        levels, live = frozen_levels

    out: dict[int, np.ndarray] = {}
    information: dict[int, np.ndarray] = {}
    separations: dict[int, float] = {}
    grid = (len(photometry), 1)
    for plane in range(N_PLANES):
        separation = float(levels[live, plane].max()
                           - levels[live, plane].min())
        separations[PLANE_NAMES[plane]] = separation
        keep = live[states]
        residual = ((levels[states[keep], plane] - centres[keep, plane])
                    / separation)
        gradient = gradients[keep, plane, :] / separation
        equations = plane_field.accumulate(
            codes[keep], gradient, residual, grid)
        a = equations.a[:, 0]
        b = equations.b[:, 0]
        eigenvalues = np.linalg.eigvalsh(a)
        delta = np.full((len(photometry), 2), np.nan)
        usable = eigenvalues[:, 0] > MIN_INFORMATION
        if np.any(usable):
            delta[usable] = np.linalg.solve(
                a[usable], b[usable][..., None])[..., 0]
        out[plane] = delta * _sheet_i.CELL_DOTS
        information[plane] = eigenvalues[:, 0]
    return out, information, separations


# --------------------------------------------------------------------
# agreement, gain, stability
# --------------------------------------------------------------------

def _rank(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="stable")
    ranks = np.empty(values.size, np.float64)
    ranks[order] = np.arange(values.size, dtype=np.float64)
    return ranks


def agreement(estimate: np.ndarray, truth: np.ndarray) -> dict:
    """Shape and scale of one estimator against one truth."""
    good = np.isfinite(estimate) & np.isfinite(truth)
    estimate = estimate[good]
    truth = truth[good]
    n = int(estimate.size)
    out: dict = {"n": n}
    if n < 4:
        return out
    out["pearson"] = float(np.corrcoef(estimate, truth)[0, 1])
    out["spearman"] = float(
        np.corrcoef(_rank(estimate), _rank(truth))[0, 1])
    nonzero = np.abs(truth) > 1e-9
    out["sign_agreement"] = float(np.mean(
        np.sign(estimate[nonzero]) == np.sign(truth[nonzero])))
    # gain through the origin: what a joint fit must divide the
    # estimator by to put it on the truth's scale
    denominator = float(np.dot(truth, truth))
    out["gain"] = (float(np.dot(estimate, truth) / denominator)
                   if denominator > 0.0 else None)
    out["rms_estimate_dots"] = float(np.sqrt(np.mean(estimate ** 2)))
    out["rms_truth_dots"] = float(np.sqrt(np.mean(truth ** 2)))
    residual = estimate - (out["gain"] or 0.0) * truth
    out["rms_residual_dots"] = float(np.sqrt(np.mean(residual ** 2)))
    return out


def bootstrap_gain(estimate: np.ndarray, truth: np.ndarray,
                   draws: int = 2000, seed: int = 20260831) -> dict:
    good = np.isfinite(estimate) & np.isfinite(truth)
    estimate = estimate[good]
    truth = truth[good]
    if estimate.size < 8:
        return {"n": int(estimate.size)}
    rng = np.random.default_rng(seed)
    gains = np.empty(draws, np.float64)
    for draw in range(draws):
        pick = rng.integers(0, estimate.size, estimate.size)
        denominator = float(np.dot(truth[pick], truth[pick]))
        gains[draw] = (np.dot(estimate[pick], truth[pick]) / denominator
                       if denominator > 0.0 else np.nan)
    finite = gains[np.isfinite(gains)]
    return {"n": int(estimate.size),
            "draws": int(finite.size),
            "p05": float(np.percentile(finite, 5.0)),
            "p50": float(np.percentile(finite, 50.0)),
            "p95": float(np.percentile(finite, 95.0))}


def _plane_relative(by_plane) -> np.ndarray:
    return by_plane[2] - 0.5 * (by_plane[0] + by_plane[1])


#: Probe shifts, in printed dots, for the response calibration.  The
#: range brackets the recorded sinusoid (0.83 dot peak) without leaving
#: the anchor's own search radius.
PROBE_SHIFTS_DOTS = (-0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75)


def response_calibration(anchor, plane_field, planes, contexts,
                         local_cells, neighbor_indices, radius_by_plane,
                         frozen_levels, shifts=PROBE_SHIFTS_DOTS,
                         block_cells: int = 0,
                         population: str = "") -> dict:
    """Each estimator's SIGN and GAIN against a displacement we authored.

    The sheet is fixed; the sampling frame moves by a known number of
    printed dots, which is the same thing as the content being displaced
    by that many dots with the opposite sign.  Everything self-referential
    -- the anchor's template, the photometric level table -- is frozen at
    the unprobed frame (see :class:`TileContext`), so what is measured is
    the estimator's response to a displacement and not its ability to
    follow its own inputs.

    An unbiased estimator of the content displacement returns a slope of
    -1 against the frame shift.  The slope's MAGNITUDE is the gain the
    record calls overshoot when it exceeds one; its SIGN is the
    convention; the spread of the per-shift medians about the line is the
    linearity.
    """
    by_estimator: dict[str, dict[int, list[float]]] = {
        "anchor": {plane: [] for plane in range(N_PLANES)},
        "photometric": {plane: [] for plane in range(N_PLANES)},
    }
    for shift in shifts:
        photometry = []
        measurements = []
        for context in contexts:
            result = measure_tile(
                anchor, planes, context, local_cells, neighbor_indices,
                radius_by_plane, probe_dots_x=shift,
                block_cells=block_cells)
            if result is None or result[1] is None:
                continue
            measurements.append(result[0])
            photometry.append(result[1])
        if not photometry:
            continue
        photometric, _information, _sep = photometric_field(
            plane_field, photometry, frozen_levels=frozen_levels)
        for plane in range(N_PLANES):
            pick = population or (POPULATION_FREE if plane == PLANE_Y
                                  else POPULATION_INK)
            values = [m.anchor_dx_dots[(plane, pick)]
                      for m in measurements
                      if (plane, pick) in m.anchor_dx_dots]
            by_estimator["anchor"][plane].append(
                float(np.median(values)) if values else np.nan)
            by_estimator["photometric"][plane].append(
                float(np.nanmedian(photometric[plane][:, 0])))

    out: dict = {"shifts_dots": list(shifts), "planes": {}}
    for plane in range(N_PLANES):
        entry: dict = {}
        for name, table in by_estimator.items():
            medians = np.asarray(table[plane], np.float64)
            good = np.isfinite(medians)
            if int(good.sum()) < 4:
                entry[name] = {"n": int(good.sum())}
                continue
            x = np.asarray(shifts, np.float64)[good]
            y = medians[good]
            slope, intercept = np.polyfit(x, y, 1)
            fitted = slope * x + intercept
            entry[name] = {
                "medians_dots": medians.tolist(),
                "slope": float(slope),
                "intercept_dots": float(intercept),
                "gain": float(-slope),
                "rms_nonlinearity_dots": float(
                    np.sqrt(np.mean((y - fitted) ** 2))),
            }
        out["planes"][PLANE_NAMES[plane]] = entry
    return out


# --------------------------------------------------------------------
# driver
# --------------------------------------------------------------------

def run(limit: int | None, out_path: Path | None, wide: bool,
        probe_tiles: bool = True, probe_stride: int = 12,
        oracle_template: bool = False, block_cells: int = 0,
        population: str = "") -> dict:
    from holo3.format import identity, tile_codec
    from holo3.lib import plane_field
    from holo3.plugins import color_model
    from holo3.plugins import color_region_anchor as anchor

    started = time.time()
    radius_by_plane = dict(RADIUS_DOTS_BY_PLANE) if wide else {}
    row = identity.resolve_format_ref(_sheet_i.FORMAT_REF)
    geometry = identity.build_site_geometry(row)
    gt_tiles = [t for t in _sheet_i.ground_truth_tiles()
                if t.common_corr >= MIN_COMMON_CORR]
    if limit is not None:
        gt_tiles = gt_tiles[:limit]
    scan = _sheet_i.open_scan()
    planes = _sheet_i.scan_planes(scan)
    local_cells = _tile_cells()
    neighbor_indices = anchor.neighbor_rows(local_cells)
    truth_dots = None
    if oracle_template and gt_tiles:
        truth_dots = _sheet_i.open_truth_dots()
        assert_cells_are_solid(truth_dots, gt_tiles[0])

    measurements: list[TileMeasurement] = []
    photometry: list[tuple] = []
    contexts: list[TileContext] = []
    kept: list[_sheet_i.GroundTruthTile] = []
    skipped = 0
    for tile in gt_tiles:
        context = tile_context(anchor, color_model, tile_codec, row,
                               geometry, planes, tile, local_cells,
                               truth_dots=truth_dots)
        if context is None:
            skipped += 1
            continue
        result = measure_tile(anchor, planes, context, local_cells,
                              neighbor_indices, radius_by_plane,
                              block_cells=block_cells)
        if result is None or result[1] is None:
            skipped += 1
            continue
        contexts.append(context)
        measurements.append(result[0])
        photometry.append(result[1])
        kept.append(tile)

    report: dict = {
        "schema": "ysampler-gt-bias-1",
        "sheet": _sheet_i.FORMAT_REF,
        "capture": str(_sheet_i.SCAN),
        "ground_truth": str(_sheet_i.REGMAP_GT),
        "decode_optimal": str(_sheet_i.SWIM),
        "search_radius_dots": {
            PLANE_NAMES[plane]: _radius_dots(
                anchor, radius_by_plane.get(plane))
            for plane in range(N_PLANES)},
        "y_radius_requested_dots": (
            radius_by_plane.get(PLANE_Y) if wide else None),
        "gt_tiles_available": len(gt_tiles),
        "gt_tiles_measured": len(kept),
        "gt_tiles_skipped": skipped,
        "template": "oracle (emitted cell field)" if oracle_template
                    else "blind reading at the pose + format furniture",
    }
    if len(kept) < 8:
        report["verdict"] = "REFUSED — too few tiles measured"
        return report

    frozen_levels = state_levels(
        np.concatenate([item[0] for item in photometry]),
        np.concatenate([item[1] for item in photometry]))
    photometric, information, separations = photometric_field(
        plane_field, photometry, frozen_levels=frozen_levels)
    report["photometric"] = {
        "plane_separation": separations,
        "tiles_informed": {
            PLANE_NAMES[plane]: int(np.count_nonzero(
                information[plane] > MIN_INFORMATION))
            for plane in range(N_PLANES)},
    }

    # Every population that produced anything, scored side by side.  The
    # default headline is production's own -- INK where the format prints
    # at a word site (C, M), FREE where it never does (Y).
    def gather(pick_for_plane) -> np.ndarray:
        table = np.full((len(kept), N_PLANES), np.nan)
        for index, measurement in enumerate(measurements):
            for plane in range(N_PLANES):
                value = measurement.anchor_dx_dots.get(
                    (plane, pick_for_plane(plane)))
                if value is not None:
                    table[index, plane] = value
        return table

    populations: dict[str, np.ndarray] = {
        "word (free on Y, ink on C/M)": gather(
            lambda plane: (POPULATION_FREE if plane == PLANE_Y
                           else POPULATION_INK)),
        "word (ink-free centres, all planes)": gather(
            lambda _plane: POPULATION_FREE),
    }
    populations["sparse furniture kernel (the production tier)"] = gather(
        lambda _plane: POPULATION_SPARSE)
    if block_cells:
        populations["furniture-only whole-tile template"] = gather(
            lambda _plane: POPULATION_FURNITURE)
    headline = (population if population in
                (POPULATION_INK, POPULATION_FREE, POPULATION_FURNITURE,
                 POPULATION_SPARSE)
                else "")
    if headline == POPULATION_SPARSE:
        anchor_mixed = populations[
            "sparse furniture kernel (the production tier)"]
    elif headline == POPULATION_FURNITURE and block_cells:
        anchor_mixed = populations["furniture-only whole-tile template"]
    elif headline == POPULATION_FREE:
        anchor_mixed = populations["word (ink-free centres, all planes)"]
    else:
        anchor_mixed = populations["word (free on Y, ink on C/M)"]
    report["anchor_population"] = headline or "free on Y, ink on C/M"

    photometric_dx = np.stack(
        [photometric[plane][:, 0] for plane in range(N_PLANES)], axis=1)
    gt_dx = np.asarray([[t.d_x_dots[plane] for plane in range(N_PLANES)]
                        for t in kept], np.float64)

    report["supply"] = _supply_table(measurements)
    report["per_tile"] = {
        "anchor_rel_dots": _plane_relative(anchor_mixed.T).tolist(),
        "photometric_rel_dots": _plane_relative(photometric_dx.T).tolist(),
        "gt_rel_dots": _plane_relative(gt_dx.T).tolist(),
        "tile_y": [t.tile_y for t in kept],
        "tile_x": [t.tile_x for t in kept],
    }

    anchor_rel = _plane_relative(anchor_mixed.T)
    photo_rel = _plane_relative(photometric_dx.T)
    gt_rel = _plane_relative(gt_dx.T)
    gt_cm = gt_dx[:, 0] - gt_dx[:, 1]
    anchor_cm = anchor_mixed[:, 0] - anchor_mixed[:, 1]

    report["by_population"] = {
        name: {
            "vs_recorded_gt_Y_relative": agreement(
                _plane_relative(table.T), gt_rel),
            "vs_gt_C_minus_M_control": agreement(
                table[:, 0] - table[:, 1], gt_cm),
        }
        for name, table in populations.items()}
    report["agreement"] = {
        "anchor_vs_gt_Y_relative": agreement(anchor_rel, gt_rel),
        "photometric_vs_gt_Y_relative": agreement(photo_rel, gt_rel),
        "anchor_vs_photometric_Y_relative": agreement(anchor_rel,
                                                      photo_rel),
        "anchor_vs_gt_C_minus_M_control": agreement(anchor_cm, gt_cm),
    }
    report["gain_stability"] = _stability(kept, anchor_rel, photo_rel,
                                          gt_rel)
    report["columns"] = _columns(kept, anchor_rel, photo_rel, gt_rel)
    report["decode_optimal_agreement"] = _swim(kept, anchor_rel, photo_rel)
    if probe_tiles:
        report["response_calibration"] = response_calibration(
            anchor, plane_field, planes, contexts[::probe_stride],
            local_cells, neighbor_indices, radius_by_plane, frozen_levels,
            block_cells=block_cells, population=population)
    report["wall_seconds"] = round(time.time() - started, 1)
    report["verdict"] = _verdict(report)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=1, sort_keys=True))
    return report


def _supply_table(measurements) -> list[dict]:
    rows = []
    for plane in range(N_PLANES):
        for population in (POPULATION_INK, POPULATION_FREE,
                           POPULATION_FURNITURE, POPULATION_SPARSE):
            key = (plane, population)
            counts = [m.anchor_n[key] for m in measurements
                      if key in m.anchor_n]
            if not counts:
                rows.append({"plane": PLANE_NAMES[plane],
                             "population": population,
                             "tiles_with_anchors": 0, "anchors": 0})
                continue
            quality = [m.anchor_quality[key] for m in measurements
                       if key in m.anchor_quality]
            saturation = [m.anchor_saturation[key] for m in measurements
                          if key in m.anchor_saturation]
            rows.append({
                "plane": PLANE_NAMES[plane],
                "population": population,
                "tiles_with_anchors": len(counts),
                "anchors": int(sum(counts)),
                "anchors_per_tile_median": float(np.median(counts)),
                "median_quality": float(np.median(quality)),
                "saturation": float(np.mean(saturation)),
            })
    return rows


def _stability(tiles, anchor_rel, photo_rel, gt_rel) -> dict:
    rows_present = sorted({t.tile_y for t in tiles})
    tile_y = np.asarray([t.tile_y for t in tiles])
    by_row = []
    for row_id in rows_present:
        pick = tile_y == row_id
        if int(pick.sum()) < 8:
            continue
        by_row.append({
            "tile_y": int(row_id),
            "n": int(pick.sum()),
            "anchor_gain": agreement(anchor_rel[pick],
                                     gt_rel[pick]).get("gain"),
            "photometric_gain": agreement(photo_rel[pick],
                                          gt_rel[pick]).get("gain"),
            "anchor_over_photometric": agreement(
                anchor_rel[pick], photo_rel[pick]).get("gain"),
        })
    gains = [r["anchor_gain"] for r in by_row
             if r["anchor_gain"] is not None]
    return {
        "by_tile_row": by_row,
        "anchor_gain_row_spread": {
            "n_rows": len(gains),
            "median": float(np.median(gains)) if gains else None,
            "min": float(np.min(gains)) if gains else None,
            "max": float(np.max(gains)) if gains else None,
        },
        "anchor_gain_bootstrap": bootstrap_gain(anchor_rel, gt_rel),
        "photometric_gain_bootstrap": bootstrap_gain(photo_rel, gt_rel),
        "anchor_over_photometric_bootstrap": bootstrap_gain(
            anchor_rel, photo_rel),
    }


def _columns(tiles, anchor_rel, photo_rel, gt_rel) -> dict:
    """The comparison the recorded sinusoid is precise at.

    Per-tile GT carries ~0.1 dot of its own noise; the recorded
    per-column means (13 rows each) are the sharp form of the sinusoid,
    so the column-level agreement is the headline shape number and the
    per-tile one is its noisy lower bound.
    """
    recorded = _sheet_i.ground_truth_columns()
    tile_x = np.asarray([t.tile_x for t in tiles])
    columns = sorted(set(tile_x.tolist()) & set(recorded))
    anchor_c, photo_c, gt_c, gt_recorded, counts = [], [], [], [], []
    for column in columns:
        pick = tile_x == column
        if int(pick.sum()) < 3:
            continue
        anchor_c.append(float(np.nanmedian(anchor_rel[pick])))
        photo_c.append(float(np.nanmedian(photo_rel[pick])))
        gt_c.append(float(np.nanmedian(gt_rel[pick])))
        gt_recorded.append(recorded[column]["rel_x_dots"])
        counts.append(int(pick.sum()))
    anchor_c = np.asarray(anchor_c)
    photo_c = np.asarray(photo_c)
    gt_recorded = np.asarray(gt_recorded)
    return {
        "n_columns": len(counts),
        "tiles_per_column_median": (float(np.median(counts))
                                    if counts else None),
        "anchor_vs_recorded_column_mean": agreement(anchor_c, gt_recorded),
        "photometric_vs_recorded_column_mean": agreement(photo_c,
                                                         gt_recorded),
        "anchor_over_photometric_column": agreement(anchor_c, photo_c),
        "recorded_rel_x_dots": gt_recorded.tolist(),
        "anchor_rel_x_dots": anchor_c.tolist(),
        "photometric_rel_x_dots": photo_c.tolist(),
        "columns": [c for c, n in zip(columns, counts)][:len(counts)],
    }


def _swim(tiles, anchor_rel, photo_rel) -> dict:
    """Estimator against the DECODE-OPTIMAL offset, where one exists.

    Ten tiles.  This is the same currency as the record's 0.93 / 1.47 /
    2.33 (docs/INDEPENDENT-PLANES.md 2.3) and just as small a sample;
    it is reported as a cross-check on the GT leg, never on its own.
    """
    index = {(t.tile_y, t.tile_x): i for i, t in enumerate(tiles)}
    rows = []
    for target in _sheet_i.swim_targets():
        if target["stream"] != "Y" or target["ber_argmin_dx"] is None:
            continue
        key = (target["tile_y"], target["tile_x"])
        if key not in index:
            continue
        position = index[key]
        rows.append({
            "tile_y": key[0], "tile_x": key[1], "band": target["band"],
            "ber_argmin_dx": target["ber_argmin_dx"],
            "anchor_rel_dots": float(anchor_rel[position]),
            "photometric_rel_dots": float(photo_rel[position]),
            "recorded_own_dust_dx": target["own_dx"],
            "recorded_regmap_rel_dx": target["regmap_rel_dx"],
        })
    if len(rows) < 2:
        return {"n": len(rows),
                "note": "no swim target coincided with a GT tile"}
    optimal = np.asarray([r["ber_argmin_dx"] for r in rows])
    return {
        "n": len(rows),
        "tiles": rows,
        "anchor_over_decode_optimal": agreement(
            np.asarray([r["anchor_rel_dots"] for r in rows]), optimal),
        "photometric_over_decode_optimal": agreement(
            np.asarray([r["photometric_rel_dots"] for r in rows]),
            optimal),
    }


def _verdict(report: dict) -> str:
    column = report["columns"]["anchor_vs_recorded_column_mean"]
    tile = report["agreement"]["anchor_vs_gt_Y_relative"]
    gain = report["gain_stability"]["anchor_gain_bootstrap"]
    pearson = column.get("pearson")
    if pearson is None or gain.get("p05") is None:
        return "REFUSED — not enough evidence to score the bar"
    stable = gain["p05"] > 0.0 and gain["p95"] / max(gain["p05"], 1e-9) < 3.0
    if pearson >= 0.7 and tile.get("sign_agreement", 0.0) >= 0.7 and stable:
        return (f"PASS — column-mean Pearson {pearson:+.3f}, per-tile sign "
                f"agreement {tile['sign_agreement']:.2f}, gain "
                f"{gain['p50']:.2f} [{gain['p05']:.2f}, {gain['p95']:.2f}]")
    return (f"FAIL — column-mean Pearson {pearson:+.3f}, per-tile sign "
            f"agreement {tile.get('sign_agreement')}, gain "
            f"{gain.get('p50')} [{gain.get('p05')}, {gain.get('p95')}]")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="measure only the first N ground-truth tiles")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--production-radius", action="store_true",
        help="keep production's plane-common search radius on Y too — "
             "the control for the per-plane radius ruling")
    parser.add_argument("--no-probe", action="store_true",
                        help="skip the response calibration")
    parser.add_argument("--probe-stride", type=int, default=12,
                        help="use every Nth measured tile for the probe")
    parser.add_argument(
        "--furniture-block", type=int, default=0,
        help="also measure a BLIND furniture-only template of this many "
             "cells a side (64 = the whole tile); 0 skips the arm")
    parser.add_argument(
        "--population", default="",
        help="which anchor population the headline uses: ink / free / "
             "furniture (default: free on Y, ink on C and M)")
    parser.add_argument(
        "--oracle-template", action="store_true",
        help="ORACLE ARM: build the anchor template from the emitted "
             "cell field instead of the pose's own blind reading — the "
             "discriminating test for template circularity")
    args = parser.parse_args(argv)
    report = run(args.limit, args.out, wide=not args.production_radius,
                 probe_tiles=not args.no_probe,
                 probe_stride=max(1, args.probe_stride),
                 oracle_template=args.oracle_template,
                 block_cells=max(0, args.furniture_block),
                 population=args.population)
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

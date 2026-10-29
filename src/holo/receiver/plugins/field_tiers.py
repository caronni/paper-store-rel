"""The page field's ONE measurement primitive, and the two templates it
correlates.

A measurement of the page field is one thing (design §2.5, W8 R-C):
correlate a KNOWN template of one plane against that plane's channel at
the owning window's pose, over a two-axis grid of page-axis offsets, and
accept only what a null-calibrated threshold admits.  Both axes, always
— the M281's dominant term is y and nothing in this line has ever
exercised it.

Two template sources, and no third, chosen PER (TILE, PLANE) against
that plane's own known mask:

* the CERTIFIED pattern of that plane.  A certificate fixes every
  printed cell of the plane it certifies, so plane p's channel is
  correlated against p's own bit image — up to 4,096 cells, measured
  gain 1.000 against an injected displacement and 0.947-1.002 against
  sheet I's recorded sinusoid.  A certified C contributes its whole
  template while M and Y are still on furniture; requiring all three
  discarded 3,976 authoritative cells per certified plane, at exactly
  the moment they are most useful (review F3).
* the FURNITURE of that plane: the format's own word and dust sites at
  their known values, available before the receiver has decoded
  anything.  Word sites carry no Y, so Y's polarity comes from the dust
  alone, which is what `ANCHOR_MIN_PER_CLASS` is about.

RETIRED 2026-09-08 (W8 R-C, design §2.5): the BLIND OFFSET tier — a
held-out log-loss sweep that selected an offset and then read the
improvement on the set it had selected on.  Driven through the
production collector by the external review, C and M printed and only Y
replaced by smooth noise, every Y anchor call was refused and 11 of 20
collections published a Y field anyway, up to 1.875 dots, spreading past
every tile anything had been observed on.  A calibrated first tier is
worth nothing if its rejection hands the same noise to an uncalibrated
second one.  With it goes the three-way parity partition, which existed
only to keep that tier's evidence independent of this one's: two sources
are disjoint by construction — payload cells against furniture sites —
so the furniture template is now that plane's WHOLE site set at the
tile.  Retired earlier, and stays retired: the linearised photometric
tier (gain 0.46-0.53 against the printer's real displacement, 1.000
against an injected one — an unexplained anomaly recorded in
docs/PAGE-FIELD-DESIGN.md §7).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..format import tile_codec
from ..format.identity import Family, FormatRow, SiteGeometry
from ..lib.geometry import TILE_CELLS
from ..lib.plane_field import SOURCE_ANCHOR, SOURCE_CERTIFIED
from . import color_model
from .color_sites import cell_dots_of, certified_projection

#: The furniture template's search radius in printed dots, per plane.
#: Project-lead ruling 2026-08-31: Y wider, C and M untouched.
#: docs/COLOR-UPLIFT-MEASUREMENTS.md §15.6 derives Y's >= 2.2 from a
#: censored p95; the harness that ruled it rectified its radius to half
#: a dot, so 2.5 was realized (this grid's own step is below).
ANCHOR_RADIUS_DOTS: tuple[float, float, float] = (1.5, 1.5, 2.5)
ANCHOR_STEP_DOTS: float = 0.25
#: The CERTIFIED template's own radius, in printed CELLS, because that
#: template is a whole tile and what bounds its search is the printed
#: cell rather than a plane's ink.  RE-DERIVED 2026-09-08 (W7b) on sheet
#: J load 1a under the FOSSIL identity `L:c2-cmy8-r0547@53x37`; the rule
#: is the smallest radius at which under 5% of the peaks this template
#: KEEPS sit at the wall (200 tiles x 3 planes, each call scoring ONE
#: radius-4.0 grid whose narrower radii are its centred sub-grids, so
#: all four saw the same photons — `scratchpad/w7b/probe_radius.py`,
#: 254 s of CPU):
#:
#:      radius  cells  cand  kept  at wall   |delta| p50 / p90 / max
#:        1.50   0.75   169   600  3 (0.5%)   0.369 / 0.746 / 1.512
#:        2.00   1.00   289   600  0          0.369 / 0.746 / 1.651
#:        2.50   1.25   441   600  0          0.369 / 0.746 / 1.651
#:        4.00   2.00  1089   600  0          0.369 / 0.746 / 1.651
#:
#: 0.75 cells passes at 0.5%, but its three wall peaks are real C
#: displacements of 1.28, 1.40 and 1.65 dots and at 0.75 cells
#: `measurement_reach_dots` bounds what this can SEE at 1.24 dots, below
#: displacements this sheet shows.  1.0 cell clears both and is refused
#: by the swim row's licence (its translation bound is one printed cell
#: and must sit inside this reach on every plane and row).  1.25 is the
#: next step up and is what ships.  What the width buys on this sheet is
#: nothing — all 600 peaks are identical from 1.0 cell outward, 598 of
#: 600 already at 0.75 — and what it costs is measured: the collection
#: goes 65.2 -> 97.7 s of CPU, +49.8%.  OPEN for the lead (design §2.5).
CERTIFIED_RADIUS_CELLS: float = 1.25
#: A template needs enough sites, and enough of the MINORITY polarity, to
#: localize: `ANCHOR_MIN_SITES` alone refuses only a template with none
#: of one class, and on this format Y carries no word ink, so its
#: polarity comes from the dust sites of a tile and a cut scrap
#: routinely leaves one or two.  Measured 2026-09-08 (W7) by driving this
#: module's own kernel with a displaced signal: a 32-site template with 1
#: minority site returns a measurement at median error 0.47 dots and
#: HIGHER quality than a balanced one, where 14 minority sites read 0.15.
ANCHOR_MIN_SITES: int = 24
ANCHOR_MIN_PER_CLASS: int = 4
#: CROSS-TALK, per family and per plane: the states whose ink darkens
#: THIS plane's channel although the plane is not printed there.  A
#: template reads one channel per plane (R for C, G for M, B for Y) and
#: labels such a cell 0, yet it carries another plane's displacement, so
#: it is weighted out of that plane's correlation and the two floors
#: above count what is left (CMY-DESIGN §7 (f)).  cmy, from the M281's
#: solid bars (e043c sheet 3, `_h3_sims_cmy.e043c_sheet3_bars`), each
#: ink's darkening of a channel against that channel's own ink: in G, C
#: 48 % and Y 6 % of M; in B, M 77 % and C 19 % of Y; in R, M 8 % and Y
#: 1 % of C.  So M's template drops C — the word's '1' — and Y's drops M —
#: the dust — and C.  C IN Y'S TEMPLATE is the design's table plus one,
#: MEASURED 2026-10-12 on the offset c3 stimulus at the render's own pose:
#: 48 C word sites at 19 % against 26 Y sites at 100 % read Y's furniture
#: 0.81 dots past the planted +1.0 (the clean render's correlation peak is
#: a plateau a dot wide, so any tilt walks the argmax along it), and C's
#: 25 % share of a certified tile read M 0.79 dots past; with both
#: weighted out every template, furniture and certified, reads within 0.09
#: dots of its in-register reading plus the plant.  M's polarity
#: then comes from its dust alone (20 sites a tile at p120), Y's from the
#: keyed Y word sites against the W ones.  cmy8 and cmy7 have no entry:
#: their templates are what they were.
CROSS_TALK_STATES: dict[Family, tuple[frozenset[int], ...]] = {
    Family.CMY: (frozenset(), frozenset({1}), frozenset({1, 2})),
}
#: A measurement at the wall is a peak-lock, not a displacement: a tenth
#: of Y anchors run to whatever radius they are given
#: (docs/COLOR-UPLIFT-MEASUREMENTS.md §15.6, the
#: saturation-by-quality-quartile table).  On sheet J load 1a under the
#: fossil the wall refuses almost nothing — 1 of 329 scored furniture
#: calls sits there and none of the 71 on Y, which the QUALITY floor
#: refuses instead, 62 of them.
ANCHOR_SATURATION_MARGIN_DOTS: float = 0.26

#: THE NULL, and what the quality floor is made of.  A weighted NCC
#: maximised over S candidates has a peak even when there is nothing to
#: find, and how big that peak is depends on the TEMPLATE SIZE: measured
#: through this module's own kernel (`offset_grid`, `weighted_ncc`,
#: `peak_offset`) against a smooth random field at the capture's own
#: sampling, the null peak times sqrt(n) is one number per grid, flat in
#: n from 24 sites to 4,096, so the null itself falls as 1/sqrt(n):
#: 0.396 at 24 sites and 0.029 at 4,096, both at radius 1.5.  ONE
#: absolute floor across that span therefore cuts at ~2x the null on a
#: whole-tile template and admits 98% of pure noise on a 24-site one
#: (2026-09-08, W7).
#:
#: WHICH NULL.  A SMOOTH random field, an image with no cell structure.
#: A plane's channel has some, which lengthens the correlation across
#: the candidate grid; drawn through the same kernel the cell-structured
#: null's MEDIAN is 0.57-0.88x this one's while its p99 moves -20% to
#: +4%, so the FLOOR is insensitive to the model and any reading of a
#: peak as a multiple of "its null" is NOT.  A null measured on a real
#: scanned plane channel is still owed (design §2.5), and it decides how
#: much a MARGINAL peak carries; this population has none — under the
#: printed identity the certified template keeps 600 of 600 calls at
#: median quality 0.820, the median call at 13.2x its own floor and the
#: worst at 6.9x.  Both draws are pinned in `tests/test_h3_field_null.py`.
#:
#: The floor is the null's own 99th percentile, so about one call in a
#: hundred keeps noise whatever the template size — re-drawn from 500
#: trials at every size the certified template uses (2026-09-08, W7
#: review), the fit tracks the measured p99 within 5% (ratios
#: 0.959-1.049 over 512...4,096 sites at radii 1.5 and 2.5) and keeps
#: 0.6-2.0% of the null.
#:
#: WHICH WAY IT MOVED, at the template sizes sheet J load 1a presents
#: under the FOSSIL (W7b): CERTIFIED templates run 1,384-4,096 sites,
#: median 3,833, where the floor reads 0.0586 over the 441-candidate
#: grid — under the absolute 0.10 this module used to carry, so it
#: ADMITS where that refused.  FURNITURE templates run 24-64 sites,
#: median 33, where it reads 0.594 on C and M's 169-candidate grid and
#: 0.631 on Y's 441 — six times 0.10, and that is where it bites: of 129
#: scored furniture-Y calls 58 stop at ANCHOR_MIN_PER_CLASS and 9 of the
#: remaining 71 clear the floor, against one refusal each of 129 on C
#: and on M.  A YIELD change ruled in direction and not in magnitude,
#: and OPEN for the lead (design §2.5).  W8 doubles the furniture
#: template by retiring the parity split, so the floor falls as
#: 1/sqrt(S) and Y's minority class doubles with it; the replays measure
#: whether that is worth anything.
NULL_P99_LN_SLOPE: float = 0.2217
NULL_P99_INTERCEPT: float = 2.2750


def certified_radius_dots(cell_dots: int) -> float:
    """The certified template's search radius on a row of this cell size."""
    return CERTIFIED_RADIUS_CELLS * float(cell_dots)


def measurement_reach_dots(plane: int, cell_dots: int) -> float:
    """How far this plane's field can be MEASURED, in printed dots.

    The largest radius any template searches on the plane, less the
    margin inside which a peak is a lock rather than a displacement.  It
    is a statement about what a correlation can SEE, and no longer a
    bound on what the solve publishes — that clip was derived in the raw
    measurement's coordinates and applied to the gauged quantity, and
    the prior governs the unmeasured region instead (design §2.4, I8).
    Its live consumer is the swim's licence: that row's translation
    bound is one printed cell and must sit inside this reach on every
    plane and row.
    """
    return (max(float(ANCHOR_RADIUS_DOTS[int(plane)]),
                certified_radius_dots(cell_dots))
            - ANCHOR_SATURATION_MARGIN_DOTS)


def min_quality(n_sites: int, n_candidates: int) -> float:
    """Below this the correlation is not a measurement, at THIS size.

    The null's own 99th percentile for a template of `n_sites` scored
    over `n_candidates`: the peak quality this kernel returns from
    nothing, 99 times in 100.  Both directions are the ones a reader
    would guess — more sites make a chance peak smaller, more candidates
    give chance more chances.
    """
    return ((NULL_P99_LN_SLOPE * float(np.log(int(n_candidates)))
             + NULL_P99_INTERCEPT) / float(np.sqrt(max(int(n_sites), 1))))


@dataclass(frozen=True)
class Template:
    """One (tile, plane)'s known bits, and where on the page they sit.

    `page_cells_yx` is (N, 2) in page cells and `bits` the printed value
    of THIS plane at each of them.  `source` says which of the two
    builders made it, and travels onto every row it measures; the
    correlation searches `radius_dots` around the pose, which is the
    template's own — a whole certified tile is bounded by the printed
    cell, a sparse furniture set by that plane's ink.  `weights` is the
    per-site weight `measure` correlates with, None for all ones: the
    family's cross-talk table (`CROSS_TALK_STATES`).
    """

    page_cells_yx: np.ndarray
    bits: np.ndarray
    source: int
    radius_dots: float
    weights: np.ndarray | None = None


def _tile_cells(ty: int, tx: int) -> np.ndarray:
    """Every cell of one tile, in page cells, in raster order."""
    local_y, local_x = np.meshgrid(np.arange(TILE_CELLS),
                                   np.arange(TILE_CELLS), indexing="ij")
    return np.stack((local_y.ravel() + int(ty) * TILE_CELLS,
                     local_x.ravel() + int(tx) * TILE_CELLS),
                    axis=1).astype(np.int64)


def certified_template(row: FormatRow, geometry: SiteGeometry, page: int,
                       tile_yx: tuple[int, int], plane: int,
                       certificates: dict,
                       memo: dict | None = None) -> Template | None:
    """This plane's whole printed tile, from its own certificate.

    None where that plane is not certified here — which is a statement
    about ONE plane: a CMY8 certificate labels its own stream and says
    nothing about the other two (`plugins/color_sites.py` is the format
    authority and always said so), so C's 4,096 cells are available
    while M and Y are still unfinished.  A cmy label stream alone knows
    no plane on the whole tile, so a cmy template needs both streams and
    then knows every cell's state, which the cross-talk weights read.
    """
    ty, tx = (int(value) for value in tile_yx)
    address = (int(page), ty, tx)
    if memo is None or address not in memo:
        projection = certified_projection(row, geometry, int(page), ty, tx,
                                          certificates)
        if memo is not None:
            memo[address] = projection
    else:
        projection = memo[address]
    if projection is None:
        return None
    bits, known = projection
    if not bool(np.asarray(known)[..., int(plane)].all()):
        return None
    states = tile_codec.planes_to_states(np.asarray(bits).reshape(-1, 3))
    return Template(page_cells_yx=_tile_cells(ty, tx),
                    bits=np.asarray(bits)[..., int(plane)].ravel(),
                    source=SOURCE_CERTIFIED,
                    radius_dots=certified_radius_dots(cell_dots_of(row)),
                    weights=cross_talk_weights(row, states, int(plane)))


def furniture_template(row: FormatRow, geometry: SiteGeometry, page: int,
                       tile_yx: tuple[int, int],
                       plane: int) -> Template | None:
    """This plane's word and dust sites at one tile, at their known values.

    Truth-free and available the moment a window is addressed: the
    receiver knows every furniture value before it reads anything.  The
    WHOLE site set, both parities — the split that used to halve it went
    with the blind tier it was keeping independent.
    """
    ty, tx = (int(value) for value in tile_yx)
    local = np.concatenate((np.asarray(geometry.word_cells_yx, np.int64),
                            np.asarray(geometry.extra_cells_yx, np.int64)))
    if not local.size:
        return None
    cells = local + np.asarray((ty * TILE_CELLS, tx * TILE_CELLS), np.int64)
    states, _kinds = color_model.reference_states(row, geometry, int(page),
                                                  cells)
    return Template(
        page_cells_yx=cells,
        bits=tile_codec.states_to_planes(states)[:, int(plane)],
        source=SOURCE_ANCHOR,
        radius_dots=float(ANCHOR_RADIUS_DOTS[int(plane)]),
        weights=cross_talk_weights(row, states, int(plane)))


def cross_talk_weights(row: FormatRow, states: np.ndarray,
                       plane: int) -> np.ndarray | None:
    """One plane's per-cell weights over these printed states: 0 where
    the family's cross-talk table names the state, 1 elsewhere, and None —
    all ones, today's bytes — for a family without an entry."""
    table = CROSS_TALK_STATES.get(row.family)
    if table is None:
        return None
    return np.where(np.isin(states, sorted(table[int(plane)])), 0.0, 1.0)


def offset_grid(radius_dots: float, step_dots: float = ANCHOR_STEP_DOTS,
                ) -> tuple[np.ndarray, int]:
    """Candidates, ``(S, 2)`` as (dx, dy) in printed PAGE-axis dots,
    and the side of the square they form.

    Square and centred, so a quarter-turn maps the grid onto itself and
    the same set of displacements is measured whatever rotation the
    scrap was placed at.
    """
    reach = max(1, int(round(float(radius_dots) / float(step_dots))))
    axis = np.arange(-reach, reach + 1, dtype=np.float64) * float(step_dots)
    grid_y, grid_x = np.meshgrid(axis, axis, indexing="ij")
    return np.stack((grid_x.ravel(), grid_y.ravel()), axis=1), axis.size


def weighted_ncc(values: np.ndarray, template: np.ndarray,
                 weights: np.ndarray) -> np.ndarray:
    """Weighted normalized cross-correlation, one score per candidate.

    ``values`` is ``(S, N)`` -- the plane sampled at N sites for each of
    S candidate displacements -- against one ``(N,)`` template.  It is
    the ordinary weighted NCC the receiver has always scored offsets
    with, on a SPARSE site set instead of a dense pixel block: a
    furniture template is ~120 known cells out of a tile's 4,096, so
    correlating whole blocks would spend 34 times the work to use the
    same evidence.
    """
    w = np.asarray(weights, np.float64)
    total = float(w.sum()) + 1e-9
    centred_template = np.asarray(template, np.float64)
    centred_template = centred_template - float(
        (centred_template * w).sum()) / total
    template_norm = np.sqrt(
        float((centred_template * centred_template * w).sum())) + 1e-9
    sampled = np.asarray(values, np.float64)
    centred = sampled - (sampled * w).sum(axis=1, keepdims=True) / total
    numerator = (centred * centred_template * w).sum(axis=1)
    norm = np.sqrt((centred * centred * w).sum(axis=1))
    return numerator / (norm * template_norm + 1e-9)


def _parabola(left: float, centre: float, right: float) -> float:
    denominator = left - 2.0 * centre + right
    if abs(denominator) < 1e-12:
        return 0.0
    return float(np.clip((left - right) / (2.0 * denominator), -0.5, 0.5))


def peak_offset(scores: np.ndarray, side: int, step_dots: float,
                grid: np.ndarray) -> tuple[np.ndarray, float]:
    """The correlation peak, refined by a parabola along each axis."""
    square = scores.reshape(side, side)
    row, column = np.unravel_index(int(np.argmax(square)), square.shape)
    shift_y = (_parabola(square[row - 1, column], square[row, column],
                         square[row + 1, column])
               if 0 < row < side - 1 else 0.0)
    shift_x = (_parabola(square[row, column - 1], square[row, column],
                         square[row, column + 1])
               if 0 < column < side - 1 else 0.0)
    base = grid[row * side + column]
    return (np.asarray((base[0] + shift_x * step_dots,
                        base[1] + shift_y * step_dots), np.float64),
            float(square[row, column]))


def minority_class(live: np.ndarray) -> int:
    """How many sites carry the rarer of the template's two values.

    The template is a plane's known BITS, so "both polarities" is the
    count of ones against the count of zeros, and a template that is all
    one value has NONE of the other.  Counting the min and the max as
    two classes said the opposite on exactly that template — a constant
    64-site one reported 64 minority sites, because min and max are the
    same value and every site is both — so it passed this gate and paid
    for a 441-candidate sweep the final NCC then threw away (review R11).
    """
    values = np.asarray(live, np.float64)
    ones = int(np.count_nonzero(values))
    return min(ones, int(values.size) - ones)


def saturated(delta_dots_xy: np.ndarray, radius_dots: float) -> bool:
    """At the wall is a peak-lock, not a displacement."""
    return bool(np.max(np.abs(np.asarray(delta_dots_xy, np.float64)))
                >= radius_dots - ANCHOR_SATURATION_MARGIN_DOTS)


@dataclass(frozen=True)
class Measured:
    """One accepted measurement: the row the collector publishes.

    `measured_xy` is a flag per AXIS and this primitive sets both — it
    searches a two-axis grid, so both axes carry a measurement (design
    §2.5, W8 R-E).  It is on the row and not implied by it because an
    axis nobody measured must be distinguishable from a measured zero,
    downstream and forever (I13).
    """

    delta_dots_xy: np.ndarray
    measured_xy: np.ndarray
    quality: float


def measure(template: Template, sample, weights: np.ndarray | None = None,
            step_dots: float = ANCHOR_STEP_DOTS) -> Measured | None:
    """Correlate one template against one plane, and accept or refuse.

    ``sample(offsets)`` takes the ``(S, 2)`` candidate grid in printed
    PAGE-axis dots and returns the ``(S, N)`` plane values at the
    template's N cells displaced by each candidate: the caller owns the
    crop and the pose and composes them into that closure, so what comes
    back is a page-axis measurement whatever orientation the scrap was
    placed at, and this owns the correlation and its three refusals.  A
    template too small or too one-sided to localize never scores, a peak
    inside its own null does not leave, and a peak at the wall is a lock
    and not a displacement.

    Ink reads DARK, so the template is correlated as ``1 - bits``: that
    convention is the primitive's, and no caller states it.
    """
    bits = np.asarray(template.bits, np.float64)
    w = (np.ones(bits.size, np.float64) if weights is None
         else np.asarray(weights, np.float64))
    live = bits[w > 0.0]
    if (live.size < ANCHOR_MIN_SITES
            or minority_class(live) < ANCHOR_MIN_PER_CLASS):
        return None
    grid, side = offset_grid(template.radius_dots, step_dots)
    values = sample(grid)
    if values is None:
        return None
    scores = weighted_ncc(values, 1.0 - bits, w)
    if not np.all(np.isfinite(scores)):
        return None
    delta, quality = peak_offset(scores, side, step_dots, grid)
    if quality < min_quality(live.size, side * side):
        return None
    if saturated(delta, template.radius_dots):
        return None
    return Measured(delta_dots_xy=delta, measured_xy=np.ones(2, bool),
                    quality=quality)

"""The page field: one per-plane registration displacement per printed
page, solved once per page from every observation any capture ever
makes of it.

A printed face carries, per ink plane, a displacement of that plane's
dots from where the format put them.  The printer puts it there and
freezes it at print time, so it is a function of page position and of
nothing else — not of the capture, the decimation level, the lane, the
platen placement or the cascade generation, which are the axes evidence
POOLS over (docs/PAGE-FIELD-DESIGN.md §2.2).  It is not small: the M281
holds its Y plane 1.7 dots off the word frame and the AltaLink's wanders
±0.83 dots with a ~100 mm period, against a c2 cell of 2 dots.

ONE PENALISED ROBUST LEAST-SQUARES PROBLEM PER PAGE, over every plane
and every window at once (design §2.6, W8 R-A/R-B).  For a row that
measured plane p on tile u through window w, the model is

    d = s_p F(u) + t_w + noise,     s_C = +1, s_M = -1 on F = F_C,
                                    s_Y = +1 on F = F_Y

so the gauge `F_C + F_M = 0` is a CONSTRAINT — M is eliminated, never
penalised — and `t_w` is one translation per window, that window's own
pose error, estimated with the fields and published to nobody.  That is
cmy8's gauge; the gauge follows the pose's ink, the row's word its proxy
(`lib/field_gauge`), and cmy's pose is C's, so there `s_C = 0` — C's
rows inform only `t_w` and `F_C` is zero by name — while M and Y are the
two free fields at `s = +1` (CMY-DESIGN R7, 2026-10-12).  The two
axes never meet: a row enters only the axes it measured, and the model
couples nothing across x and y, so the page is two independent systems.

The objective, per axis, over the two free fields and the nuisances:

    sum_i  rho( w_i (s F(u_i) + t_i - d_i) )        the evidence
  + F' (lambda_c L^2 + lambda_g L + lambda_z I) F   the prior

where `L` is the tile grid's own Laplacian, so the prior is smoothness
(curvature and gradient) plus a pull toward zero, and its three weights
come from two PHYSICAL LENGTHS and one share — the physics is the
printer's and does not know the cell pitch (`default_prior`).  `rho` is
Huber: a lane that latched onto a wrong correlation minimum is off by a
whole grid step, and one such row may not drag a tile.  Reweighting runs
to that loss's OWN FIXED POINT and not to a pass count, so what is
published is the stated objective's optimum (`WEIGHT_TOLERANCE`) — with
one exception, a page that spends `IRLS_MAX_PASSES` without settling,
which publishes the iterate it reached and says `converged` False.

Nothing here reads a clock, draws a random number, or touches a raster:
the caller measures, this module fits and evaluates.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import linalg, ndimage, sparse

from . import field_gauge
from .evidence import Rows
from .field_gauge import CM_WORD_PLANES, Gauge
from .geometry import TILE_CELLS

#: The three colour planes, in the order the format names them.  K has
#: one plane and no differential, so it has no field at all.
N_PLANES: int = 3

#: What share of the smoothness penalty the GRADIENT term carries, the
#: rest being curvature.  The design names two LENGTHS and a quadratic
#: in the Laplacian has three weights, so one number is left over, and
#: this is it — the only one of the prior's that is not a length.  It
#: buys the monotone fade: curvature alone matches the last measured
#: SLOPE and carries it onward, so a page measured only where a wave is
#: steep publishes an excursion of the wrong sign past its evidence.
#: MEASURED on the behaviour suite's own stimuli, 2026-09-08 (the sweep
#: report was not retained; the measured values are the ones stated
#: here): at 0.02 the field past twice the fade length reads 0.53
#: dots against a 0.25-dot bar, and at 0.5 an isolated four-tile
#: island loses a fifth of a 1.5-dot injected displacement.  0.2 holds
#: both, and puts the fast decay root
#: at twice the smoothing length — the longest reach over which the
#: last measured slope is still absorbed inside the smooth model's own.
#: THAT SWEEP WAS RUN AT 10.8 mm and its upper end is gone: with the
#: smoothing length derived from the gain bar below, the same four-tile
#: island reads its own injection to 0.052-0.058 dots at EVERY share
#: from 0.2 to 1.0 (measured 2026-09-08, the length re-derived at each
#: share).  0.2 stays, unruled and unmoved (design §2.4).
GRADIENT_SHARE: float = 0.2

#: THE BAR THE SMOOTHING LENGTH IS DERIVED FROM (the lead's ruling,
#: 2026-09-08).  The field exists to resolve page-scale registration
#: structure, and the structure this record has actually measured is the
#: AltaLink's ~100 mm Y sinusoid (design §0), so the solve must KEEP at
#: least this much of a wave that long, at every pitch.  A length copied
#: from a retired filter's bandwidth is not a bar; this is, and the
#: length below is its solution rather than an inheritance.
GAIN_BAR: float = 0.95
GAIN_WAVELENGTH_MM: float = 100.0
#: What the FINITE PAGE takes off the ideal transfer the derivation
#: solves, so that the design point sits INSIDE the bar rather than on
#: it.  The transfer is an infinite-grid statement; the fourth-order
#: term's free-end stencil over-penalises the tiles within a few of the
#: page's own edge, and how much of the wave that costs depends on where
#: the edges cut it.  MEASURED 2026-09-08 at the derivation's own
#: length, as shortfalls against GAIN_BAR: 0.0101 at c2 and 0.0009 at c3
#: on the behaviour suite's 20x40 page, 0.0086 and 0.0082 on the 53-row
#: page this format prints (and none at all on the 37-row one) — while
#: the page's INTERIOR reads the transfer exactly, 0.9491 measured
#: against 0.9492 predicted.  Rounded up to 0.015 so the bar has room:
#: at the shipped length the measured gain clears GAIN_BAR by 0.0066 on
#: the worst of six page-and-pitch combinations.  Set it to zero and
#: the length is the bar's own root, 6.373 mm, where the solve measures
#: 0.9399 at c2 — the bar as ruled would not be met (design §2.4).
PAGE_EDGE_LOSS: float = 0.015


def _smoothing_length_mm() -> float:
    """`SMOOTHING_LENGTH_MM`, solved from `GAIN_BAR` at `GAIN_WAVELENGTH_MM`.

    The penalty is a quadratic in the Laplacian, so its Fourier symbol is
    `S(k) = lambda_g k^2 + lambda_c k^4` (the pull toward zero adds
    `lambda_z`, four parts in a thousand at this length and ignored
    here), and the fit's transfer against one measurement per tile is
    `1 / (1 + S(k))`.  The normalisation `S(1/l_s) = 1` makes that
    `g (k l_s)^2 + (1 - g) (k l_s)^4` with `g = GRADIENT_SHARE`, so
    asking the transfer for `GAIN_BAR + PAGE_EDGE_LOSS` at
    `k = 2 pi / GAIN_WAVELENGTH_MM` is one quadratic in `(k l_s)^2` with
    one positive root: `k l_s = 0.3492`, `l_s = 5.557 mm`.
    """
    wavenumber = 2.0 * np.pi / GAIN_WAVELENGTH_MM
    stiffness = 1.0 / (GAIN_BAR + PAGE_EDGE_LOSS) - 1.0
    curvature = 1.0 - GRADIENT_SHARE
    squared = ((-GRADIENT_SHARE
                + np.sqrt(GRADIENT_SHARE ** 2 + 4.0 * curvature * stiffness))
               / (2.0 * curvature))
    return float(np.sqrt(squared) / wavenumber)


#: The smoothness penalty's length, in millimetres, DERIVED from the two
#: bar constants above and `GRADIENT_SHARE` — 5.557 mm, where the W7
#: tree carried 10.8 mm copied from the retired tile-pinned bandwidth
#: (2.0 tiles x 5.419 mm at c2).  That copy passed only 0.776 of the
#: 100 mm wave at c2 and 0.791 at c3 where the kernel it was named after
#: passed 0.957 — same length, different filter (design §2.4).  MEASURED
#: at the shipped length, 2026-09-08: 0.957 at c2 and 0.965 at c3 on the
#: behaviour suite's own stimulus, both over `GAIN_BAR`, at the price of
#: passing 0.059 dots rms of pure noise where 10.8 mm passed 0.030.
SMOOTHING_LENGTH_MM: float = _smoothing_length_mm()
#: The half-value length of the pull toward zero, in millimetres: half
#: the same period.  A tile this far from every measurement keeps at
#: most half of the nearest one and the fall continues, so a tile twice
#: as far keeps at most a quarter — 0.21 dots of the largest field this
#: record has measured, under `FIELD_NOISE_DOTS`, which is why "reads
#: the pose" is a bar and not a hope (design §2.4).  UNCHANGED at the
#: 2026-09-08 gain fix, and the two roots separate FURTHER at the
#: shorter smoothing length: the fade's slow root decays over 72.1 mm
#: and the smoothing's fast root over twice the smoothing length, 11.1
#: mm, a ratio of 6.5 where 10.8 mm gave 3.3.
FADE_LENGTH_MM: float = 50.0

#: One scale for every observation's noise, in printed dots.  The
#: weights are RELEVANCE weights — an NCC quality — not inverse
#: variances, so the fit needs its own scale, and this is the anchor
#: tier's own search step (`plugins/field_tiers.ANCHOR_STEP_DOTS`): a
#: residual under a quarter dot is at the measurement's resolution.
FIELD_NOISE_DOTS: float = 0.25
#: Huber's knee, in noise scales: the textbook 1.345, which costs 5% of
#: the Gaussian's efficiency and bounds one wrong-minimum row's pull at
#: that row's weight times the knee.
HUBER_KNEE: float = 1.345
#: THE FIXED POINT, on the Huber MULTIPLIER: a fit is accepted when the
#: multipliers recomputed from its own residual agree with the ones that
#: produced it, to this much on the loudest row.  A NUMERICAL tolerance
#: on a dimensionless number in (0, 1], not a physical one — what it
#: accepts is the objective's own optimum, and a tolerance chosen loose
#: enough to be felt would publish a different estimator.  It replaces
#: three unconditional passes, which were NOT the fixed point and were
#: documented as if they were ("all but binary after the first
#: reweight"): on five captures of one c3 tile, two of them a whole grid
#: step out, those three passes published Y 0.783843 at an objective
#: gradient of 0.337180 where the optimum is 0.336051 at 4e-16, and on
#: nine captures 1.125119 where the optimum is 0.403356 (the external
#: review's `estimator_repros.py`, 2026-09-09).
WEIGHT_TOLERANCE: float = 1e-6
#: A ceiling on those passes, so a page that will not settle costs a
#: bounded amount.  REPORTED, never a refusal: the objective is convex
#: and every pass is a descent step on it, so the capped iterate is the
#: best answer reached and is published with `converged` False beside
#: it, where a refusal would publish nothing at all.
#: WHAT SPENDS THE PASSES IS THE RESIDUAL SCALE, not the contamination:
#: passes are bought by rows sitting near and past the knee, and a FEW
#: PERCENT of them is enough, because every reweight moves the answer and
#: re-sorts which rows those are.  At this module's own declared
#: observation scale — `FIELD_NOISE_DOTS`, knee 0.336 dots — 1.9% (c3)
#: to 3.8% (c2) of the residuals of a CLEAN page stand outside the knee
#: on the noise alone, and they cost 14 passes; the same page measured at
#: the suite's quiet 0.10 leaves none outside and costs one.
#: MEASURED 2026-09-12, passes to the fixed point, every number
#: named with the noise it was taken at:
#: 1 pass on the estimator suite's full-support sinusoid AS THAT SUITE
#: MEASURES IT, at its quiet 0.10 dots, where no row leaves the knee —
#: the field and its uncertainty come out BIT-IDENTICAL to the three
#: passes' there, in 0.20 s of cpu against 0.24; 14 at both pitches on
#: that same page with its noise raised to 0.25; 13 (c2) and 17 (c3) on
#: the contaminated stimulus with its wrong rows switched OFF, and 13
#: and 21 with 5% of every plane's rows a whole cell out, so the
#: contamination buys at most four of those passes and the noise buys
#: the rest; 11 and 15 on the review's two contaminated single-tile
#: toys; 16 (c2) and 22 (c3) on a 53x37 page carrying 60 windows and
#: 5,883 rows at 0.25, 23 at c3 with the contamination, about 0.6 s of
#: wall a pass.  On THAT page the three unconditional passes stood
#: 0.013 to 0.094 dots from the optimum, a real fraction of the quarter
#: dot this fit resolves.  A solve's share of its page's collection
#: (design §2.7, bar B6) was measured at three passes and this
#: multiplies it by the pass count: those ratios are owed a
#: re-measurement.
#: THE ONE CASE MEASURED OVER THIS CEILING is the review's
#: 1x2 two-window toy, whose two disagreeing rows sit near the knee and
#: whose multipliers crawl: 212 passes to the fixed point — inside the
#: ceiling since the lead raised it from 50 to 250 (2026-09-12), so the
#: capped path is pinned by forcing the ceiling in-process (`tests/
#: test_h3_field_estimator.py`).
IRLS_MAX_PASSES: int = 250

#: Where an observation came from (design §2.5).  The blind tier was 2
#: and is retired; the numbers of the two that survive do not move,
#: because archived facts carry them.
SOURCE_CERTIFIED: int = 0
SOURCE_ANCHOR: int = 1
SOURCE_NAMES: tuple[str, ...] = ("certified", "anchor")

# The retired kernel smoother's two constants and its two functions.
# Nothing in this receiver smooths a field any more; `analyzer/field2`
# builds its own parametric surface with them, at production's recorded
# bandwidth, and `analyzer/arms` reads its mass through the same taps —
# the same standing they have as `MAX_DELTA_DOTS` and `clamp` below.
BANDWIDTH_TILES: float = 2.0
KERNEL_TRUNCATION: float = 3.5
TWICING_PASSES: int = 1
# A ceiling this receiver does not apply to a field (I8), kept because
# `analyzer/field2` clamps its own surface at production's number.
MAX_DELTA_DOTS: float = 2.0

_LN2: float = float(np.log(2.0))


# ----------------------------------------------------------- the prior

@dataclass(frozen=True)
class Prior:
    """The three weights of one polynomial in the tile grid's Laplacian,
    and what the last of them is worth as a statement of ignorance.

    `sigma_dots` is the standard deviation the pull toward zero carries
    on its own, which is what a tile no evidence ever reaches publishes
    as its uncertainty.
    """

    cell_dots: int
    dots_per_mm: float
    tile_mm: float
    smoothing_mm: float
    fade_mm: float
    gradient_weight: float
    curvature_weight: float
    zero_weight: float
    sigma_dots: float


def default_prior(cell_dots: int, dots_per_mm: float) -> Prior:
    """Design §2.4's two lengths, at this pitch, on this printer.

    `lib/` names no printer, so the SCALE that turns a millimetre into a
    tile is handed in — `HW_DPI / MM_PER_INCH`, the format's constant —
    and never reached for from here.

    THE ALGEBRA, in ten lines.  The penalty is one quadratic polynomial
    in `L`, the tile grid's own Laplacian, so its Fourier symbol is
    `S(k) = lambda_z + lambda_g k^2 + lambda_c k^4`, and one unit of
    weight is one measurement at the design's noise scale, so the fit's
    transfer function against one such row per tile is `1 / (1 + S(k))`.

    - `S(1/l_s) = 1` fixes the SMOOTHING length: at that wavenumber the
      prior is exactly as stiff as one measurement per tile, so
      `lambda_g / l_s^2 + lambda_c / l_s^4 = 1`, and `GRADIENT_SHARE`
      says which term pays which part of it.
    - Away from evidence `S` has two decay roots.  The slow one,
      `sqrt(lambda_z/lambda_g)`, is the FADE: `lambda_z = lambda_g
      (ln2 / L_f)^2` makes the field halve every `L_f`, and the fast
      one, `sqrt(lambda_g/lambda_c)`, absorbs the last measured slope
      within twice the smoothing length instead of carrying it onward,
      which is what makes the fall MONOTONE.
    - `sigma_dots = FIELD_NOISE_DOTS / sqrt(lambda_z)` = 7.26 dots at
      every pitch (3.73 before the smoothing length was derived from the
      gain bar, which took the gradient weight down and the ridge with
      it): an honestly uninformative number for a quantity this record
      has never measured past 2.

    Both lengths become tiles first, which is why a c2 and a c3 page are
    smoothed the same physical amount.
    """
    tile_mm = TILE_CELLS * int(cell_dots) / float(dots_per_mm)
    smoothing_tiles = SMOOTHING_LENGTH_MM / tile_mm
    fade_tiles = FADE_LENGTH_MM / tile_mm
    gradient = GRADIENT_SHARE * smoothing_tiles ** 2
    zero = gradient * (_LN2 / fade_tiles) ** 2
    return Prior(cell_dots=int(cell_dots), dots_per_mm=float(dots_per_mm),
                 tile_mm=tile_mm, smoothing_mm=SMOOTHING_LENGTH_MM,
                 fade_mm=FADE_LENGTH_MM, gradient_weight=gradient,
                 curvature_weight=(1.0 - GRADIENT_SHARE)
                 * smoothing_tiles ** 4,
                 zero_weight=zero,
                 sigma_dots=FIELD_NOISE_DOTS / np.sqrt(zero))


def _laplacian(length: int) -> np.ndarray:
    """One tile axis's Laplacian, `D1' D1` with free ends.

    A page one tile wide along an axis has no neighbours there and
    contributes nothing, which is a statement about the page and not a
    special case: the other axis and the pull toward zero still hold the
    system down.
    """
    steps = max(0, int(length) - 1)
    difference = np.zeros((steps, int(length)), np.float64)
    for step in range(steps):
        difference[step, step:step + 2] = (-1.0, 1.0)
    return difference.T @ difference


def _grid_laplacian(tiles_yx: tuple[int, int]) -> sparse.csr_array:
    """The page's own Laplacian: the two axes' Kronecker sum."""
    height, width = int(tiles_yx[0]), int(tiles_yx[1])
    return sparse.csr_array(
        sparse.kron(sparse.eye_array(height),
                    sparse.csr_array(_laplacian(width)))
        + sparse.kron(sparse.csr_array(_laplacian(height)),
                      sparse.eye_array(width)))


def _penalty(tiles_yx: tuple[int, int], prior: Prior) -> sparse.csr_array:
    """One field's penalty: `lambda_z I + lambda_g L + lambda_c L^2`."""
    laplacian = _grid_laplacian(tiles_yx)
    height, width = int(tiles_yx[0]), int(tiles_yx[1])
    return sparse.csr_array(
        prior.zero_weight * sparse.eye_array(height * width)
        + prior.gradient_weight * laplacian
        + prior.curvature_weight * (laplacian @ laplacian))


def _prior_variance(tiles_yx: tuple[int, int], prior: Prior) -> np.ndarray:
    """`(height, width)`: what one field's variance is before any
    evidence, exactly.

    The penalty is a polynomial in a Kronecker SUM, so its eigenvectors
    are the outer products of the two axes' own and the inverse's
    diagonal is one weighted sum over the pairs.  Exact, and it costs
    two small symmetric eigendecompositions rather than the inverse of a
    whole page.

    It is not constant over the grid: a corner tile has fewer neighbours
    to be smooth against, so it starts out less determined than an
    interior one.  That is why `solve` publishes the posterior on this
    quantity's own scale (`_uncertainty`).
    """
    moments = [np.linalg.eigh(_laplacian(length))
               for length in (int(tiles_yx[0]), int(tiles_yx[1]))]
    (down, vectors_y), (across, vectors_x) = moments
    spectrum = down[:, None] + across[None, :]
    coupling = 1.0 / (prior.zero_weight
                      + prior.gradient_weight * spectrum
                      + prior.curvature_weight * spectrum ** 2)
    return (vectors_y ** 2) @ coupling @ (vectors_x ** 2).T


# ------------------------------------------------------------ the solve

@dataclass(frozen=True)
class Residual:
    """How loudly one capture's measurements of one plane disagree."""

    energy: float
    weight: float
    count: int

    @property
    def expected(self) -> float:
        """The energy consistent measurements carry anyway: one noise
        scale per measured component, since the weights are relevance
        weights and not inverse variances."""
        return FIELD_NOISE_DOTS ** 2 * self.weight


@dataclass(frozen=True)
class Solution:
    """One page's three fields and everything the solve knows about them.

    `nuisance_dots_xy` is the one thing here that is NOT publishable: it
    is per WINDOW, and a per-window displacement that reached the fact
    stream would be a per-window field under another name and the next
    reader would sample through it (design §2.6).  It is returned for
    the diagnostics and the harness, which read it in this process.

    `revision` is the evidence revision the fit was made at (design
    §2.6's last bullet, I12).  The solve does not read it; it carries it
    so that a solution is self-describing and its event needs nothing
    but the solution to name what it was fitted on.

    `passes`, `converged` and `max_gradient` are the fit's own account of
    its iteration, each the WORSE of the two axes: how many reweighted
    solves it took, whether the Huber multipliers reached their fixed
    point inside `IRLS_MAX_PASSES`, and the largest component of the
    TRUE objective's gradient at the published answer, in weight-dots.
    A capped fit is published and says so; the gradient is the number
    that says whether the answer is the specified estimator's or an
    iterate on the way to it.  They default to one settled pass — what a
    Solution assembled by hand rather than fitted is, there being no
    iteration to account for — and `_fit_axis` is the only producer that
    ever sets them to anything else.
    """

    delta_dots_xy: np.ndarray
    uncertainty_dots: np.ndarray
    support: np.ndarray
    n_observations: np.ndarray
    n_captures: np.ndarray
    plane_known: np.ndarray
    nuisance_dots_xy: np.ndarray
    residual_by_capture_plane: dict[tuple[int, int], Residual]
    revision: int
    passes: int
    converged: bool
    max_gradient: float

    @property
    def tiles_yx(self) -> tuple[int, int]:
        """The page's tile grid, which the fields ARE."""
        return (int(self.delta_dots_xy.shape[1]),
                int(self.delta_dots_xy.shape[2]))


def _check_codes(tile_code: np.ndarray, tiles_yx: tuple[int, int]) -> None:
    """Every tile code names a tile of this page's grid.

    A negative code indexes from the far edge and an over-large one
    raises a bare numpy error, so the codes are checked where they
    enter.
    """
    codes = np.asarray(tile_code, np.int64)
    height, width = int(tiles_yx[0]), int(tiles_yx[1])
    if codes.size and (int(codes.min()) < 0
                       or int(codes.max()) >= height * width):
        raise ValueError(
            f"page field: tile code outside a {height}x{width} grid "
            f"({int(codes.min())}..{int(codes.max())})")


def _huber(residual: np.ndarray, knee: float) -> np.ndarray:
    """Huber's weight: 1 inside the knee, `knee/|r|` outside, so a row
    that is a whole grid step wrong pulls with a bounded force instead
    of its square."""
    size = np.abs(np.asarray(residual, np.float64))
    return np.where(size <= knee, 1.0, knee / np.maximum(size, 1e-12))


#: How many columns of the inverse are asked for at once.  The whole
#: identity in one call is the same arithmetic and a third of a gigabyte
#: of transients on the largest page this format prints, beside a decode
#: already holding several gigabytes.  Measured 2026-09-08 on a 53x37
#: page carrying 5,883 rows: the peak RSS of a 1,600-window confetti
#: solve falls 2.59 -> 1.90 GB and of a 60-window solve 0.74 -> 0.56, for
#: 15 % of the solve's own time (3.46 -> 3.99 s).
_INVERSE_COLUMNS: int = 1024


def _inverse_diagonal(factor: tuple, n_total: int,
                      n_field: int) -> np.ndarray:
    """The posterior variance of the field unknowns, exactly.

    The factor is the fit's own, so this is the marginal posterior of
    the fields with the window nuisances already integrated out — which
    is what makes a tile measured only through one window's rows read
    as uncertain as it really is.
    """
    variance = np.empty(n_field, np.float64)
    for start in range(0, n_field, _INVERSE_COLUMNS):
        stop = min(start + _INVERSE_COLUMNS, n_field)
        columns = np.arange(stop - start)
        unit = np.zeros((n_total, stop - start), np.float64)
        unit[np.arange(start, stop), columns] = 1.0
        variance[start:stop] = linalg.cho_solve(
            factor, unit)[np.arange(start, stop), columns]
    return variance


@dataclass(frozen=True)
class _AxisFit:
    """One axis's answer: the two free fields, the nuisances, the
    posterior variance of the fields, and what the iteration cost."""

    field: np.ndarray
    nuisance: np.ndarray
    variance: np.ndarray
    residual: np.ndarray
    passes: int
    converged: bool
    max_gradient: float


@dataclass(frozen=True)
class _Design:
    """One axis's static design: which unknown every row touches, what it
    measured, and the penalty padded with the windows' own unpenalised
    block.  Everything a reweighted pass needs except the weights.
    """

    sign: np.ndarray
    column: np.ndarray
    nuisance_column: np.ndarray
    down: np.ndarray
    across: np.ndarray
    delta: np.ndarray
    weight: np.ndarray
    padded: sparse.csr_array
    used: np.ndarray
    n_total: int


def _design(rows: Rows, axis: int, n_field: int,
            penalty: sparse.csr_array, gauge: Gauge) -> _Design:
    """The unknowns are the two fields' tiles and then one translation
    per window THAT MEASURED THIS AXIS — a window with no row here has
    no parameter, which is what keeps the matrix positive definite
    without inventing a prior for a pose nobody observed.  Which field a
    row's plane reads, and at what sign, is the gauge's.
    """
    plane = np.asarray(rows.plane, np.int64)
    field_column, coefficient = gauge
    column = (field_column[plane] * (n_field // 2)
              + np.asarray(rows.tile_code, np.int64))
    used, compact = np.unique(np.asarray(rows.window, np.int64),
                              return_inverse=True)
    nuisance_column = n_field + compact
    return _Design(
        sign=coefficient[plane], column=column,
        nuisance_column=nuisance_column,
        down=np.concatenate([column, column, nuisance_column,
                             nuisance_column]),
        across=np.concatenate([column, nuisance_column, column,
                               nuisance_column]),
        delta=np.asarray(rows.delta_dots_xy, np.float64)[:, axis],
        weight=np.asarray(rows.weight, np.float64),
        padded=sparse.block_diag(
            (penalty, sparse.csr_array((used.size, used.size))),
            format="csr"),
        used=used, n_total=n_field + used.size)


def _weighted_matrix(design: _Design, active: np.ndarray) -> np.ndarray:
    """`A' W A + P` at these weights, dense.

    Assembled sparsely — a row touches exactly one tile and one window,
    so the whole page is four entries per row — and handed over dense:
    the largest page this format prints is 53x37 tiles, so the matrix is
    at most about 2 x 1,961 + windows on a side, and the factor of THIS
    matrix is also what gives the posterior diagonal exactly, which is
    the number design §2.4 publishes beside every tile.  What the
    density costs PER PASS, measured 2026-09-08 on that page with 5,883
    rows: 4.0 s and 0.56 GB for a 60-window solve, 9.2 s and 1.90 GB for
    a 1,600-window confetti one, against a collection's 1,921.6 s on
    sheet H — the ratio design §2.7 states is that times the pass count,
    and `IRLS_MAX_PASSES` carries what those counts measure.
    """
    matrix = sparse.coo_array(
        (np.concatenate([active * design.sign ** 2, active * design.sign,
                         active * design.sign, active]),
         (design.down, design.across)),
        shape=(design.n_total, design.n_total))
    return (matrix + design.padded).toarray()


def _weighted_target(design: _Design, active: np.ndarray) -> np.ndarray:
    """`A' W d` at these weights: one accumulation into every unknown a
    row touches, the gauge's sign on the field half."""
    return np.bincount(
        np.concatenate([design.column, design.nuisance_column]),
        weights=np.concatenate([active * design.sign * design.delta,
                                active * design.delta]),
        minlength=design.n_total)


def _stationarity(design: _Design, answer: np.ndarray,
                  residual: np.ndarray, penalty: sparse.csr_array,
                  n_field: int) -> float:
    """The largest component of the TRUE objective's gradient at this
    answer, over the fields and the nuisances alike, in weight-dots.

    The objective is `sum_i w_i rho(r_i) + F' P F / 2`, so its gradient
    is the prior's push on the fields plus, on every unknown a row
    touches, that row's weight times its BOUNDED influence
    `clip(r, -knee, knee)`.  The reweighted normal equations solve
    exactly this condition once the multipliers stop moving, which is
    why the fixed point is the optimum and not a place the iteration
    happened to stop.
    """
    knee = HUBER_KNEE * FIELD_NOISE_DOTS
    force = design.weight * np.clip(residual, -knee, knee)
    # float64 spelled out: `bincount` of an EMPTY index array returns
    # int64 whatever the weights are, and an axis no row measured is an
    # ordinary state here (I13)
    gradient = np.asarray(np.bincount(
        np.concatenate([design.column, design.nuisance_column]),
        weights=np.concatenate([design.sign * force, force]),
        minlength=design.n_total), np.float64)
    gradient[:n_field] += penalty @ answer[:n_field]
    return float(np.max(np.abs(gradient), initial=0.0))


def _fit_axis(rows: Rows, axis: int, n_field: int,
              penalty: sparse.csr_array, gauge: Gauge) -> _AxisFit:
    """The penalised robust fit of one axis, by iteratively reweighted
    least squares on the normal equations, TO THE FIXED POINT.

    A pass solves the normal equations at the standing Huber
    multipliers, then recomputes the multipliers from its own residual;
    the answer is accepted when those agree to `WEIGHT_TOLERANCE`, which
    is the stationarity condition of the objective itself, or when
    `IRLS_MAX_PASSES` passes have been spent, which is reported and not
    refused.  The variance then comes from a factor of the matrix at the
    ACCEPTED answer's own consistent weights: the last factor inside the
    loop was built from the weights of the pass BEFORE it, and at a
    capped fit those are the stale ones.
    """
    design = _design(rows, axis, n_field, penalty, gauge)
    knee = HUBER_KNEE * FIELD_NOISE_DOTS
    # the first pass is the plain weighted least squares the old three
    # started from: every multiplier one, nothing reweighted yet
    multiplier = np.ones_like(design.weight)
    passes, converged = 0, False
    while passes < IRLS_MAX_PASSES and not converged:
        active = design.weight * multiplier
        answer = linalg.cho_solve(
            linalg.cho_factor(_weighted_matrix(design, active)),
            _weighted_target(design, active))
        residual = (design.sign * answer[design.column]
                    + answer[design.nuisance_column] - design.delta)
        consistent = _huber(residual, knee)
        converged = bool(np.max(np.abs(consistent - multiplier),
                                initial=0.0) <= WEIGHT_TOLERANCE)
        multiplier = consistent
        passes += 1

    # only the matrix: the variance is a property of the factor, and the
    # accepted answer is already in hand
    variance = _inverse_diagonal(
        linalg.cho_factor(_weighted_matrix(design,
                                           design.weight * multiplier)),
        design.n_total, n_field)
    nuisance = np.zeros(int(design.used.max()) + 1 if design.used.size
                        else 0, np.float64)
    nuisance[design.used] = answer[n_field:]
    return _AxisFit(
        field=answer[:n_field].reshape(2, -1), nuisance=nuisance,
        variance=variance.reshape(2, -1), residual=residual,
        passes=passes, converged=converged,
        max_gradient=_stationarity(design, answer, residual, penalty,
                                   n_field))


def solve(rows: Rows, tiles_yx: tuple[int, int], *, cell_dots: int,
          prior: Prior, revision: int = 0,
          word: tuple[int, ...] = CM_WORD_PLANES) -> Solution:
    """One page, every plane and every window at once (design §2.6).

    The gauge is `word`'s, the planes the row's word prints: cmy8's
    eliminates M, so the unknown fields are C's and Y's, and under cmy's
    C is zero by name and they are M's and Y's.  The
    windows carry the pose errors; the two axes are solved separately
    because a row measures each on its own (I13) and nothing in the
    model couples them.  Both components everywhere, with no floor, no
    gate and no clip — what this produces is what the readers sample
    through, and support, counts, uncertainty and the per-(capture,
    plane) residuals are REPORTED beside it (design §2.6, I8).

    A page with no evidence solves to zero everywhere with the prior's
    own uncertainty, which is the honest statement that nothing is known
    and the pose is what readers should use.  It is reached, not
    returned early: removal is a state (I13).

    `revision` is a label the fit carries and never reads; it defaults
    to the store's own zero, which is what `store.evidence_revision`
    answers for a page whose evidence has never changed.
    """
    if int(cell_dots) != prior.cell_dots:
        raise ValueError(
            f"page field: a prior built at c{prior.cell_dots} cannot "
            f"price a c{int(cell_dots)} page")
    rows.sole_page()
    gauge = field_gauge.gauge_table(word)
    height, width = int(tiles_yx[0]), int(tiles_yx[1])
    n_tiles = height * width
    _check_codes(rows.tile_code, (height, width))

    one_field = _penalty((height, width), prior)
    penalty = sparse.csr_array(sparse.block_diag((one_field, one_field),
                                                 format="csr"))
    field = np.zeros((2, n_tiles, 2), np.float64)
    variance = np.zeros((2, n_tiles, 2), np.float64)
    n_windows = (int(np.asarray(rows.window, np.int64).max()) + 1
                 if len(rows) else 0)
    nuisance = np.zeros((n_windows, 2), np.float64)
    residual = np.zeros((len(rows), 2), np.float64)
    measured = np.asarray(rows.measured_xy, bool)
    passes, converged, max_gradient = 0, True, 0.0
    for axis in (0, 1):
        live = measured[:, axis] & (np.asarray(rows.weight, np.float64) > 0.0)
        fit = _fit_axis(rows.select(live), axis, 2 * n_tiles, penalty,
                        gauge)
        field[..., axis] = fit.field
        variance[..., axis] = fit.variance
        nuisance[:fit.nuisance.size, axis] = fit.nuisance
        residual[live, axis] = fit.residual
        # the page's account of the iteration is the WORSE of its two
        # independent systems: one axis settling says nothing about the
        # other, and a reader asking "is this the optimum" wants the no
        passes = max(passes, fit.passes)
        converged = converged and fit.converged
        max_gradient = max(max_gradient, fit.max_gradient)

    grids = np.stack(field_gauge.plane_fields(field, gauge)).reshape(
        N_PLANES, height, width, 2)
    return Solution(
        delta_dots_xy=grids,
        uncertainty_dots=_uncertainty(variance, (height, width), prior,
                                      gauge),
        plane_known=_plane_known(rows, gauge), nuisance_dots_xy=nuisance,
        residual_by_capture_plane=_residuals(rows, residual),
        revision=int(revision), passes=passes, converged=converged,
        max_gradient=max_gradient, **_counts(rows, (height, width)))


def _uncertainty(variance: np.ndarray, tiles_yx: tuple[int, int],
                 prior: Prior, gauge: Gauge) -> np.ndarray:
    """`(3, height, width)`: how much of what nothing-is-known is worth
    still stands at each tile, in dots.

    The posterior variance from the fit's own factor, pooled over the
    two axes (the prior is isotropic and the primitive measures both),
    divided by the same tile's PRIOR variance and put back on the
    prior's scale.  The ratio is what the evidence removed; reporting it
    this way rather than as a bare posterior deviation is what makes a
    page with no evidence anywhere read `sigma_dots` EXACTLY at every
    tile, corners included — the prior's own variance is not constant on
    a finite grid, because a corner tile has fewer neighbours to be
    smooth against.

    BOUNDED ABOVE by `sigma_dots`, and NOT MONOTONE in the evidence.
    At any FIXED set of weights the posterior variance is never larger
    than the prior's it came from, so the ratio never exceeds one and
    the published number never exceeds `sigma_dots`; but the weights are
    the robust loss's and are not fixed — evidence that CONFLICTS with
    what stands re-weights the rows that were already there, and a tile
    can come out less determined than it was.  MEASURED on a c3 1x2 page
    (the external review, 2026-09-09; re-measured against the shipped
    code 2026-09-12): one window measuring Y at 3.25 dots on tile 0
    publishes 0.431956 there, converged in one pass, and adding a second
    window measuring every plane at zero on tile 1 takes it to 0.458141
    at its fixed point, +6.06 % — reached at 212 passes, inside the
    250-pass ceiling; at the 50-pass ceiling this shipped with for an
    hour the capped iterate read 0.465298, +7.7 %, and the rise is in
    both.  Agreeing evidence shrinks
    it; conflicting evidence is entitled to make the page less sure of
    itself, and a number forced downward would be hiding that.  Under
    cmy8's gauge M's is C's, the two being one unknown; a plane the gauge
    holds at the pose has none and reads zero.

    It is therefore NOT the posterior deviation — 18.1x it on the
    behaviour suite's stimulus, measured 2026-09-08 at the derived
    smoothing length (19.4x at the 10.8 mm the tree carried before it) —
    and which of the two a reader should be shown is design §2.4's open
    question.
    """
    pooled = np.stack(field_gauge.plane_variances(variance, gauge)).mean(
        axis=2)
    at_rest = _prior_variance(tiles_yx, prior).reshape(-1)
    return (prior.sigma_dots * np.sqrt(pooled / at_rest)).reshape(
        N_PLANES, int(tiles_yx[0]), int(tiles_yx[1]))


def _plane_known(rows: Rows, gauge: Gauge) -> np.ndarray:
    """Which planes this page has a measurement of (I13).

    A plane with no template reads UNKNOWN and not zero; planes reading
    one field stand together, and a plane the gauge holds at the pose is
    known by name (`field_gauge.known_planes`).
    """
    live = (np.asarray(rows.weight, np.float64) > 0.0) \
        & np.any(np.asarray(rows.measured_xy, bool), axis=1)
    return field_gauge.known_planes(
        np.unique(np.asarray(rows.plane, np.int64)[live]), gauge)


def _counts(rows: Rows, tiles_yx: tuple[int, int]) -> dict:
    """Per (plane, tile): the pooled weight, the observations and the
    captures behind them.  Reported, never a gate (design §2.6)."""
    height, width = int(tiles_yx[0]), int(tiles_yx[1])
    cells = N_PLANES * height * width
    live = (np.asarray(rows.weight, np.float64) > 0.0) \
        & np.any(np.asarray(rows.measured_xy, bool), axis=1)
    cell = (np.asarray(rows.plane, np.int64)[live] * (height * width)
            + np.asarray(rows.tile_code, np.int64)[live])
    once = np.unique(np.stack(
        [cell, np.asarray(rows.capture, np.int64)[live]], axis=1), axis=0)
    return dict(
        support=np.bincount(
            cell, weights=np.asarray(rows.weight, np.float64)[live],
            minlength=cells).reshape(N_PLANES, height, width),
        n_observations=np.bincount(cell, minlength=cells).astype(
            np.int64).reshape(N_PLANES, height, width),
        n_captures=np.bincount(once[:, 0], minlength=cells).astype(
            np.int64).reshape(N_PLANES, height, width))


def _residuals(rows: Rows, residual: np.ndarray,
               ) -> dict[tuple[int, int], Residual]:
    """The fit's residual per (capture, PLANE), never summed across
    planes first.

    A hundred explained C rows, a hundred explained M rows and one Y row
    a dot out give Y a ratio of 8 and the summed report 0.040: healthy
    word-plane evidence hides exactly the poorly supported Y this
    diagnostic exists to expose (design §2.6, the review's F11).
    """
    weight = np.asarray(rows.weight, np.float64)[:, None] \
        * np.asarray(rows.measured_xy, bool)
    energy = weight * residual ** 2
    out: dict[tuple[int, int], Residual] = {}
    keys = np.stack([np.asarray(rows.capture, np.int64),
                     np.asarray(rows.plane, np.int64)], axis=1)
    for key in np.unique(keys, axis=0) if len(rows) else ():
        group = np.all(keys == key, axis=1)
        out[(int(key[0]), int(key[1]))] = Residual(
            energy=float(energy[group].sum()),
            weight=float(weight[group].sum()),
            count=int(group.sum()))
    return out


# ------------------------------------------------------- the evaluation

def tile_codes(cells_yx: np.ndarray, tiles_yx: tuple[int, int],
               tile_cells: int) -> np.ndarray:
    cells = np.asarray(cells_yx, np.int64)
    return ((cells[:, 0] // tile_cells) * tiles_yx[1]
            + cells[:, 1] // tile_cells)


def evaluate(delta_dots_xy: np.ndarray, cells_yx: np.ndarray,
             tile_cells: int) -> np.ndarray:
    """Bilinear lookup at tile centres, clamped at the page edge.

    PER CELL, never once per tile or window: the AltaLink's sinusoid
    reaches 0.28 dots per tile, up to 0.9 dots across one 200-cell
    window at its zero crossings.
    """
    delta = np.asarray(delta_dots_xy, np.float64)
    cells = np.asarray(cells_yx, np.float64)
    if not cells.shape[0]:
        return np.zeros((0, 2), np.float64)
    coordinates = np.stack(
        (np.clip(cells[:, 0] / tile_cells - 0.5, 0.0,
                 delta.shape[0] - 1.0),
         np.clip(cells[:, 1] / tile_cells - 0.5, 0.0,
                 delta.shape[1] - 1.0)), axis=0)
    out = np.empty((cells.shape[0], 2), np.float64)
    for axis in (0, 1):
        out[:, axis] = ndimage.map_coordinates(
            delta[..., axis], coordinates, order=1, mode="nearest")
    return out


def median_magnitude_dots(delta_dots_xy: np.ndarray,
                          support: np.ndarray) -> float:
    """Median |delta| over tiles that actually carry evidence."""
    delta = np.asarray(delta_dots_xy, np.float64)
    live = np.asarray(support, np.float64) > 0.0
    if not np.any(live):
        return 0.0
    magnitude = np.hypot(delta[..., 0], delta[..., 1])
    return float(np.median(magnitude[live]))


# ------------------------------------------- the analyzer's own kernel

def gaussian_kernel(bandwidth_tiles: float = BANDWIDTH_TILES,
                    truncation: float = KERNEL_TRUNCATION) -> np.ndarray:
    """Unnormalised (peak 1) Gaussian taps: information adds, it never
    averages away."""
    radius = max(1, int(np.ceil(truncation * bandwidth_tiles)))
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    return np.exp(-0.5 * (offsets / float(bandwidth_tiles)) ** 2)


def smooth(grid: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Separable correlation with one kernel on both tile axes,
    zero-padded."""
    values = np.asarray(grid, np.float64)
    for axis in (0, 1):
        values = ndimage.correlate1d(values, np.asarray(kernel, np.float64),
                                     axis=axis, mode="constant", cval=0.0)
    return values


def clamp(delta_dots_xy: np.ndarray,
          max_delta_dots: float = MAX_DELTA_DOTS) -> np.ndarray:
    """Bound a delta's magnitude.

    Nothing in this receiver clamps a page field: the prior, not a
    bound, governs the unmeasured region (I6, I8).  The function
    survives because `analyzer/field2` builds its own parametric surface
    and bounds it here, at production's own recorded ceiling.
    """
    delta = np.asarray(delta_dots_xy, np.float64)
    magnitude = np.hypot(delta[..., 0], delta[..., 1])
    scale = np.where(magnitude > max_delta_dots,
                     max_delta_dots / np.maximum(magnitude, 1e-12), 1.0)
    return delta * scale[..., None]

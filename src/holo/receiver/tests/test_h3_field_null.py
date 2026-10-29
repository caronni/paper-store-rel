"""The one primitive's NULL, and the quality floor cut from it.

`plugins/field_tiers.min_quality` is the one constant in the page-field
line whose value is a measurement of this receiver's own kernel rather
than of a printer, so it gets its own module: the table below IS the
measurement, and the tests are the ways it can go wrong.

TWO of the four kept at W8 (2026-09-08, settled at the spec review):
`min_quality` is not retired with the tiers — it is the acceptance of
the ONE surviving measurement primitive (design §2.5, R-C), so its
calibration keeps a direct pin.  The two that went: the 1/sqrt(sites)
shape test, which was the calibration of the retired blind tier, and
"the shipped floor refuses the null it was fitted to", which is bar
B9's end-to-end question asked of one kernel and is proved through the
whole collector in `test_h3_field_evidence.py`.

Split out of `test_h3_plane_fields.py` at the W7 review (2026-09-08),
which measured that module at 1,359 lines and 9.78 s serial as one
xdist `loadgroup` — the fast lane's critical path.  A separate module is
a separate group, and the null draws are the heaviest thing in it.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import ndimage

from holo.receiver.plugins import field_tiers

#: The measured NULL of the correlation kernel: per (radius, template
#: sites), the median and the 99th percentile of the peak quality when
#: the template's bits are independent of the ink, with the trial count
#: each was drawn from.  Measured 2026-09-08 (W7) through
#: `offset_grid`/`weighted_ncc`/`peak_offset` against a smooth random
#: field at 4 px per printed dot, c2 cells; the run is
#: `scratchpad/w7/null_final.py` and its table is reproduced live below
#: at the two cheapest sizes.
#:
#: RE-DRAWN 2026-09-08 (W7 review, `scratchpad/fix/null_big.py`): every
#: row at 512 sites and up came from 40-250 trials, which is under the
#: 500 the floor test binds at, so the fit was pinned only where the
#: certified tier never operates — its templates run 1,384 to 4,096
#: sites, median 3,833, on sheet J load 1a under the printed identity
#: `L:c2-cmy8-r0547@53x37` (RE-READ 2026-09-08, W7b; the "47 to 4,096,
#: median 2,278" this comment carried was the re-keyed seed's run, and
#: the correction only strengthens the argument).  Those eight rows are now 500-trial
#: draws.  The fit HELD: it tracks the re-drawn p99 within 5% at every
#: one of them, over a 16x extension of the support it was fitted on.
NULL_TABLE: dict[float, tuple[tuple[int, float, float, int], ...]] = {
    1.5: ((24, 0.3958, 0.6774, 1000), (32, 0.3431, 0.5893, 1000),
          (64, 0.2349, 0.4277, 1000), (128, 0.1621, 0.3087, 500),
          (256, 0.1204, 0.2140, 500), (512, 0.0829, 0.1437, 500),
          (1024, 0.0582, 0.1025, 500), (2240, 0.0398, 0.0752, 500),
          (4096, 0.0298, 0.0545, 500)),
    2.5: ((24, 0.4803, 0.7083, 1000), (32, 0.4146, 0.6137, 1000),
          (64, 0.2919, 0.4622, 1000), (128, 0.2041, 0.3459, 500),
          (256, 0.1438, 0.2321, 500), (512, 0.1021, 0.1582, 500),
          (1024, 0.0724, 0.1126, 500), (2240, 0.0488, 0.0798, 500),
          (4096, 0.0359, 0.0578, 500)),
    4.0: ((24, 0.5402, 0.7164, 1000), (32, 0.4715, 0.6615, 1000),
          (64, 0.3339, 0.4781, 1000), (128, 0.2338, 0.3527, 500),
          (256, 0.1664, 0.2491, 500))}

#: THE SAME DRAW, PAIRED, against two image models: the smooth random
#: field the shipped floor was fitted to, and a CELL-STRUCTURED one — a
#: pseudorandom binary pattern on the format's own 2-dot lattice under
#: the same PSF, which is what a plane's channel actually looks like.
#: One run, so the two columns are comparable trial for trial; the table
#: above is a different, larger draw and its medians are not.  Measured
#: 2026-09-08 (W7 review, `scratchpad/rev_null.py`, seed 7, 200 trials
#: at 24 and 256 sites, 60 at 1,024), as
#: (sites, smooth median, cells median, smooth p99, cells p99).
NULL_TABLE_CELLS: dict[
        float, tuple[tuple[int, float, float, float, float], ...]] = {
    1.5: ((24, 0.3738, 0.2393, 0.6563, 0.6048),
          (256, 0.1219, 0.0732, 0.2106, 0.1746),
          (1024, 0.0583, 0.0333, 0.0935, 0.0960)),
    2.5: ((24, 0.4587, 0.4013, 0.7165, 0.6447),
          (256, 0.1431, 0.1153, 0.2515, 0.2004),
          (1024, 0.0707, 0.0573, 0.1036, 0.1076))}

PX_PER_DOT, CELL_DOTS, MARGIN_PX = 4.0, 2, 48


def _null_peaks(n_sites: int, radius: float, trials: int,
                seed: int = 7, cells: bool = False) -> np.ndarray:
    """The peak quality this kernel returns when there is nothing there.

    A template of `n_sites` on the format's own cell lattice, its bits
    drawn INDEPENDENTLY of the ink, correlated against a random field at
    the capture's own sampling.  `cells` chooses the image: smooth, the
    one the shipped table and the floor were fitted to, or the cell
    lattice a real channel carries.
    """
    rng = np.random.default_rng(seed)
    grid, side = field_tiers.offset_grid(radius)
    k = int(np.ceil(np.sqrt(n_sites)))
    span = int(np.ceil(k * CELL_DOTS * PX_PER_DOT)) + 2 * MARGIN_PX
    cell_px = int(CELL_DOTS * PX_PER_DOT)
    yy, xx = np.meshgrid(np.arange(k), np.arange(k), indexing="ij")
    cy = MARGIN_PX + yy.ravel()[:n_sites] * CELL_DOTS * PX_PER_DOT
    cx = MARGIN_PX + xx.ravel()[:n_sites] * CELL_DOTS * PX_PER_DOT
    peaks = np.empty(trials)
    for trial in range(trials):
        if cells:
            coarse = rng.integers(
                0, 2, (span // cell_px + 2,) * 2).astype(np.float64)
            image = np.kron(coarse, np.ones((cell_px, cell_px)))[:span,
                                                                 :span]
        else:
            image = rng.standard_normal((span, span))
        image = ndimage.gaussian_filter(image, 2.0)
        bits = rng.integers(0, 2, n_sites).astype(np.float64)
        values = np.empty((grid.shape[0], n_sites))
        for index, (dx, dy) in enumerate(grid):
            values[index] = ndimage.map_coordinates(
                image, [cy + dy * PX_PER_DOT, cx + dx * PX_PER_DOT],
                order=1)
        peaks[trial] = field_tiers.peak_offset(
            field_tiers.weighted_ncc(values, 1.0 - bits,
                                     np.ones(n_sites)),
            side, field_tiers.ANCHOR_STEP_DOTS, grid)[1]
    return peaks


def test_the_quality_floor_is_that_null_s_own_ninety_ninth_percentile():
    """One false accept in about a hundred, at every recorded size.

    A multiple of the null's MEDIAN cannot do this: at 24 sites the
    median is 0.396 and 2.5x it is over 1.0, which no correlation can
    reach.  The band is what the fit was measured to hold to, and the
    trial floor is why it may be believed: every row of the table is a
    500-trial draw, so the assertion binds at the sizes the certified
    tier actually uses (47 ... 4,096) and not only where the p99 was
    fitted (24 ... 256).  A p99 from 40 draws is a maximum.
    """
    for radius, rows in NULL_TABLE.items():
        _grid, side = field_tiers.offset_grid(radius)
        for n_sites, _median, p99, trials in rows:
            assert trials >= 500, (radius, n_sites, trials)
            ratio = field_tiers.min_quality(n_sites, side * side) / p99
            assert 0.90 <= ratio <= 1.12, (radius, n_sites, ratio)


def test_the_floor_survives_the_null_s_model_and_a_peak_ratio_does_not():
    """Which half of this measurement depends on the image it was made
    against, found at the W7 review.

    A real plane channel is not a smooth field; it is cells.  Longer
    correlation across the candidate grid means fewer effective tries,
    so the null's MEDIAN falls — 0.57 to 0.88 of the smooth model's,
    paired — while its p99 moves only -20% to +4%.  The floor is cut
    from the p99, so the floor stands whichever model is right, and its
    keep-rate under the alternative is the lower of the two.  A peak
    read as a multiple of "its null" is the statistic that flips, by up
    to 1.7x at radius 1.5.

    The sheet-J instance this docstring carried — 339 certified peaks at
    0.70 of their null under the smooth model and 1.17 under this one,
    "the difference between that tier measured nothing and it measured
    something" — is WITHDRAWN (2026-09-08, W7b).  That replay declared
    the re-keyed display name, so the tier was correlating against
    another row's bits; read under the fossil the same tier's peaks sit
    at a median 13.2x their own floor over 600 of 600 calls, worst 6.9x,
    which neither null model comes near.  The ratio still flips, and
    what a null measured on a real scanned channel would decide is a
    MARGINAL peak.
    """
    for radius, rows in NULL_TABLE_CELLS.items():
        for n_sites, smooth_median, median, smooth_p99, p99 in rows:
            assert median <= 0.90 * smooth_median, (radius, n_sites)
            assert 0.75 <= p99 / smooth_p99 <= 1.10, (radius, n_sites)
    _grid, side = field_tiers.offset_grid(1.5)
    floor = field_tiers.min_quality(24, side * side)
    live = _null_peaks(24, 1.5, 200, cells=True)
    assert np.median(live) == pytest.approx(
        NULL_TABLE_CELLS[1.5][0][2], rel=0.08)
    assert np.mean(live >= floor) <= 0.005

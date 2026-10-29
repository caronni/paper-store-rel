"""`analyzer.harmonic` — one sinusoid fit, and it is the honest one.

The 2026-09-13 review's F7: the two page-field products fitted a
harmonic to a DETRENDED profile without taking the trend out of the
harmonic columns too, which is not the same estimate as fitting
`[1, x, cos, sin]` together.  Over 37 columns a real sinusoid is
strongly collinear with a line, so the old recipe handed part of the
sinusoid to the trend and published what was left as a physical
amplitude.

What is pinned here is the correction and its reach: the review's own
noiseless cases come back at the planted amplitude and the planted
period, INCLUDING the two with no trend in the data at all (the sharper
half of the finding — the bias was never about the data being tilted);
nan columns and a profile that is a line behave as they did; and the two
products call this one function rather than carrying a copy each.
"""

from __future__ import annotations

import ast
import pathlib

import numpy as np
import pytest

from analyzer import harmonic
from analyzer import passfiles
from analyzer.sweeps import field2_paper as sweep

#: The review's stimulus: `0.8·sin(2πx/P + φ) + 0.4 + 0.01x`, 37 columns.
COLUMNS = 37
AMPLITUDE = 0.8
TREND_PER_COLUMN = 0.01


def profile_of(period: float, phase: float, *, trend: float) -> np.ndarray:
    x = np.arange(COLUMNS, dtype=np.float64)
    return (AMPLITUDE * np.sin(2.0 * np.pi * x / period + phase) + 0.4
            + trend * x)


def fitted(profile, *, mm_per_tile: float = 1.0) -> dict:
    """The analyzer's own grid, which is what both products search."""
    return harmonic.fit_sinusoid(
        profile, period_min_tiles=harmonic.PERIOD_MIN_TILES,
        period_step=harmonic.PERIOD_STEP_TILES, mm_per_tile=mm_per_tile)


# ------------------------------------------------- the review's cases

@pytest.mark.parametrize("period,phase,trend,was", (
    # period, phase, trend in the data, and what the two-step fitter read
    (18.5, 0.00, TREND_PER_COLUMN, 0.691838),
    (18.5, 1.57, TREND_PER_COLUMN, 0.796724),
    (37.0, 0.00, TREND_PER_COLUMN, 0.509676),
    # …and with NO trend in the data: the bias is the fitter removing the
    # sinusoid's own projection onto the line, not the data being tilted
    (18.5, 0.00, 0.0, 0.691022),
    (37.0, 0.00, 0.0, 0.509676),
))
def test_a_planted_sinusoid_comes_back_at_its_own_amplitude(period, phase,
                                                            trend, was):
    """F7: 0.8000 at the planted period, where the two-step read `was`.

    The tolerance is four decimals because the data is noiseless and the
    planted periods are ON the 0.25-tile grid: this is an exact recovery,
    not an approximation, and a fit that drifts off it has stopped being
    the joint one.
    """
    got = fitted(profile_of(period, phase, trend=trend))
    assert got["amplitude_dots"] == pytest.approx(AMPLITUDE, abs=5e-5)
    assert got["period_tiles"] == pytest.approx(period)
    assert got["r_squared"] == pytest.approx(1.0, abs=1e-9)
    assert got["n_live_columns"] == COLUMNS
    assert got["fit"] == harmonic.FIT_NAME
    # the old number is the thing being left behind, not matched
    assert abs(was - AMPLITUDE) > 1e-3


def test_the_recovered_trend_is_the_one_left_in_the_data():
    """The joint fit's trend, with the harmonic's share given back.

    The two-step reported the tilt of the RAW profile, which is the
    planted trend plus whatever of the sinusoid projected onto it; the
    joint one is the planted trend over the page, 0.01 x 36 columns.
    """
    over_the_page = TREND_PER_COLUMN * (COLUMNS - 1)
    with_tilt = fitted(profile_of(18.5, 0.0, trend=TREND_PER_COLUMN))
    flat = fitted(profile_of(18.5, 0.0, trend=0.0))
    assert with_tilt["trend_dots_per_page"] == pytest.approx(over_the_page,
                                                             abs=5e-5)
    assert flat["trend_dots_per_page"] == pytest.approx(0.0, abs=5e-5)


@pytest.mark.parametrize("planted", (0.0, np.pi / 2.0, -0.8))
def test_the_phase_is_reported_in_the_convention_the_docstring_names(planted):
    """`amplitude · cos(2πx/period - phase_rad)`, x the column index.

    The stimulus is a SINE of phase `planted`, so the reported cosine
    phase is `π/2 - planted` — pinned against the closed form rather
    than against another fit, because the whole point of the number is
    that two planes' phases can be subtracted.  Phase is what tells a
    common-mode sinusoid from a differential one (the review's F8);
    amplitude and period together cannot, and two profiles a quarter
    period apart carry the same both.
    """
    got = fitted(profile_of(18.5, planted, trend=0.0))
    assert got["amplitude_dots"] == pytest.approx(AMPLITUDE, abs=5e-5)
    wrapped = float(np.angle(np.exp(1j * (got["phase_rad"]
                                          - (np.pi / 2.0 - planted)))))
    assert wrapped == pytest.approx(0.0, abs=1e-3)


# ----------------------------------------------- the profiles that are not

def test_a_nan_holed_profile_is_fitted_on_the_columns_it_has():
    """Columns no evidence reached drop out; the PAGE does not shrink.

    The grid's top is the profile's full length, holes included, so a
    page with a gap in it still has a period as long as the page.
    """
    holed = profile_of(18.5, 0.0, trend=TREND_PER_COLUMN)
    holed[[3, 4, 19]] = np.nan
    got = fitted(holed, mm_per_tile=2.0)
    assert got["amplitude_dots"] == pytest.approx(AMPLITUDE, abs=5e-5)
    assert got["period_tiles"] == pytest.approx(18.5)
    assert got["period_mm"] == pytest.approx(37.0)
    assert got["n_live_columns"] == COLUMNS - 3
    assert got["profile"][3] is None and got["profile"][0] is not None


def test_a_flat_profile_has_no_sinusoid_and_a_short_one_has_no_fit():
    """A plane no observation reached reads zero everywhere.

    Two different refusals, and they say different things: a profile
    that IS a line has a denominator of zero and no harmonic to report
    against it, and a profile with fewer live columns than the fit has
    parameters is not an estimate at all.
    """
    flat = fitted(np.zeros(COLUMNS))
    assert flat["amplitude_dots"] is None and flat["period_tiles"] is None
    assert flat["r_squared"] == 0.0
    assert flat["trend_dots_per_page"] == 0.0
    assert flat["n_live_columns"] == COLUMNS

    short = np.full(COLUMNS, np.nan)
    short[:harmonic.MIN_LIVE_COLUMNS - 1] = 1.0
    refused = fitted(short)
    assert refused["n_live_columns"] == harmonic.MIN_LIVE_COLUMNS - 1
    assert all(refused[name] is None for name in
               ("amplitude_dots", "period_tiles", "period_mm", "r_squared",
                "phase_rad", "trend_dots_per_page"))
    # …and it still names its definition, so a refusal is readable too
    assert refused["fit"] == harmonic.FIT_NAME


def test_a_ramp_gives_the_whole_page_to_the_trend_and_nothing_to_a_wave():
    """The bounded grid is searched for a harmonic, not for a tilt.

    A pure ramp is a line to within float, not exactly, so some period
    does win the search — and what it wins with is an amplitude at
    machine zero.  That is the number a reader has to be able to trust:
    `r_squared` off a denominator of 1e-31 means nothing, and the
    amplitude says the fit found nothing, which is the truth.
    """
    ramp = fitted(np.arange(COLUMNS, dtype=np.float64) * 0.03)
    assert abs(ramp["amplitude_dots"]) < 1e-12, ramp["amplitude_dots"]
    assert ramp["trend_dots_per_page"] == pytest.approx(0.03 * (COLUMNS - 1))


# ---------------------------------------------- one copy, and it is blind

def test_both_products_fit_through_this_module_and_agree():
    """F7's other half: the sweep's and the in-run product's two copies.

    They were byte-identical source held in step by a twin test; they are
    now the same call, and the twin test in
    `test_analyzer_fixedpoint.py` compares both against this module.
    """
    profile = profile_of(16.0, 0.3, trend=TREND_PER_COLUMN)
    mine = sweep.sinusoid_fit(profile, sweep.MM_PER_TILE)
    theirs = passfiles._field2_sinusoid(profile, sweep.MM_PER_TILE)
    assert mine == theirs == fitted(profile, mm_per_tile=sweep.MM_PER_TILE)
    assert mine["fit"] == harmonic.FIT_NAME


def test_harmonic_imports_no_analyzer_module_at_all():
    """PLAN §0's import rule, at its strongest for this module.

    `passfiles` is on the blind run path and the sweep reads
    `analyzer.truth`, so the shared helper may not reach a sweep — and
    the cheapest way to be sure of that forever is to import nothing of
    the analyzer's whatsoever, which is also all a pure fit needs.
    """
    tree = ast.parse(pathlib.Path(harmonic.__file__).read_text("utf-8"))
    named: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            named.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            named.add("." * node.level + (node.module or ""))
    assert named == {"__future__", "numpy"}, sorted(named)

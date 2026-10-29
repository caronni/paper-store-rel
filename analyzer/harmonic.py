"""The one harmonic fit the analyzer's two page-field products share.

BLIND.  Nothing here may import :mod:`analyzer.truth` or
:mod:`analyzer.oracle` — and nothing here may import a SWEEP either.
That is the whole reason this module exists as a module: the sweep
(`sweeps/field2_paper.py`) reads truth, the in-run product
(`passfiles.py`) may not reach anything that does, and the two publish
the same `sinusoid_x` to the same reader (`measure/page_field/
compare.py`).  Before 2026-09-13 they held two byte-identical copies of
the arithmetic kept in step by a twin test; the copies now call here.

WHAT THE FIT IS, and why it changed (review 2026-09-13, F7).  The old
copies removed a linear trend from the PROFILE and then fitted plain
`cos`/`sin` columns to the residual.  That is not the same estimate as
fitting a trend and a harmonic together, because the harmonic columns
carry their own projection onto the line: over a 37-column page a
genuine sinusoid is strongly collinear with a tilt, so the two-step
recipe hands part of the sinusoid to the trend and reports what is
left.  Measured on noiseless data — `0.8·sin(2πx/P + φ) + 0.4 + 0.01x`,
x = 0…36 — the two-step reads amplitude 0.692 at P = 18.5, φ = 0, and
0.510 at P = 37; and it reads 0.691 at P = 18.5 with NO trend in the
data at all, which is the sharper statement: the bias is the fitter
removing the sinusoid's own projection onto the line, not the data
having a tilt.  The joint fit returns 0.8000 in every one of those
cases.  On the sheet-H profiles of record the correction is +2.5 % to
+15 % of amplitude and up to +0.6 tiles of period.

So the design here is Frisch-Waugh: residualise BOTH the profile and
the two harmonic columns against `[1, x]`, then solve.  That is exactly
`[1, x, cos, sin]` in one least squares, at one extra solve per
candidate period, and it keeps the cheap bounded period grid the old
copies searched.  The reported `r_squared` keeps the old denominator —
the DETRENDED sum of squares — so the number still answers "how much of
what the tilt left does the harmonic explain"; only the numerator's
design matrix changed.  The trend reported beside it is the JOINT one,
the tilt with the harmonic's share given back.

Every returned dict names its definition in `fit`, so a product written
before this ruling is distinguishable from one written after it by
reading the product rather than its date.
"""

from __future__ import annotations

import numpy as np

#: What `fit` says.  An older product carries no `fit` key at all and
#: was fitted the two-step way; anything that has to tell them apart
#: reads this key's presence, not a timestamp.
FIT_NAME = "joint-trend-harmonic"

#: The analyzer's own period grid, in tiles — the one both page-field
#: products search.  The bottom is four tiles because nothing shorter is
#: a page-scale registration wave; the step is the sweep's, and the top
#: is the profile's WHOLE length, so a period longer than the page is
#: reported as the page rather than folded onto a shorter one.
#: `compare.py` searches the same range at a finer step and passes its
#: own; that is why these are arguments and not constants of the fit.
PERIOD_MIN_TILES: float = 4.0
PERIOD_STEP_TILES: float = 0.25

#: Fewer live columns than this and there is no fit to report.  Four
#: free parameters over a profile this short is not an estimate, and the
#: honest row says so in Nones rather than in a number.
MIN_LIVE_COLUMNS: int = 8


def fit_sinusoid(profile: np.ndarray, *, period_min_tiles: float,
                 period_step: float, mm_per_tile: float) -> dict:
    """Least-squares amplitude and period of the best single sinusoid.

    A grid over period in tiles with a linear solve at each — the
    profile is 37 points, so this is exact enough and needs no
    optimiser.  Columns no evidence reached come in as nan and are
    dropped from the solve (the grid's top is still the profile's full
    length, holes included: a hole does not shorten the page); the fit
    refuses below :data:`MIN_LIVE_COLUMNS` of them.

    `mm_per_tile` is the caller's, from the rung it is running on, and
    it is the only thing here that is not a pure function of the
    profile.
    """
    values = np.asarray(profile, np.float64)
    live = np.isfinite(values)
    n_live = int(np.count_nonzero(live))
    stated = {"fit": FIT_NAME, "n_live_columns": n_live,
              "profile": [None if not np.isfinite(value) else float(value)
                          for value in values]}
    if n_live < MIN_LIVE_COLUMNS:
        return {"amplitude_dots": None, "period_tiles": None,
                "period_mm": None, "r_squared": None, "phase_rad": None,
                "trend_dots_per_page": None, **stated}

    x = np.flatnonzero(live).astype(np.float64)
    y = values[live]
    line = np.column_stack((np.ones_like(x), x))
    tilt, *_ = np.linalg.lstsq(line, y, rcond=None)
    detrended = y - line @ tilt
    total = float(detrended @ detrended)
    span = float(x[-1] - x[0])

    best = {"amplitude_dots": None, "period_tiles": None, "period_mm": None,
            "r_squared": 0.0, "phase_rad": None,
            "trend_dots_per_page": float(tilt[1] * span), **stated}
    if total <= 0.0:
        # A profile that IS a line — a plane no observation reached
        # reads zero everywhere — has no harmonic to find and no
        # denominator to report one against.
        return best

    for period in np.arange(period_min_tiles,
                            float(values.size) + 0.01, period_step):
        angle = 2.0 * np.pi * x / period
        harmonic = np.column_stack((np.cos(angle), np.sin(angle)))
        # Frisch-Waugh: the harmonic columns lose their own projection
        # onto `[1, x]` too, which is what makes this the joint fit.
        projection, *_ = np.linalg.lstsq(line, harmonic, rcond=None)
        residualised = harmonic - line @ projection
        solution, *_ = np.linalg.lstsq(residualised, detrended, rcond=None)
        residual = float(np.sum((detrended - residualised @ solution) ** 2))
        r_squared = 1.0 - residual / total
        if r_squared > best["r_squared"]:
            best = {"amplitude_dots": float(np.hypot(*solution)),
                    "period_tiles": float(period),
                    "period_mm": float(period * float(mm_per_tile)),
                    "r_squared": float(r_squared),
                    # `amplitude · cos(2πx/period - phase_rad)`, x the
                    # column index, so two planes' phases subtract.
                    "phase_rad": float(np.arctan2(solution[1], solution[0])),
                    "trend_dots_per_page": float(
                        (tilt[1] - projection[1] @ solution) * span),
                    **stated}
    return best

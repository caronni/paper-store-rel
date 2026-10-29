"""The frame the field is measured in, and the pose error that is not it.

W8 charter §3, items 11-12, written BEFORE the build (R-G), and R-A is
the rule they express.

The old rule subtracted, inside each window, the weighted average of
whatever C and M measurements that window happened to keep.  The zero of
the field therefore moved with which planes a scanner saw and how much
weight they carried: the review held the physical displacements fixed at
C = +0.6, M = -0.6, Y = +1.5 dots and read Y back as +0.9, +2.1 or +1.5
depending on visibility alone — 1.2 dots of swing on a page that never
moved (F1).

R-A puts the frame where the printer put it.  The word ink is C and M
overprinted, so the two word planes are DEFINED to cancel each other at
every tile (`F_C + F_M = 0`), and each window carries ONE unknown
translation of its own — its pose error — estimated with the fields and
published to nobody.  A window that saw one word plane still helps,
because the smooth field ties its tiles to its neighbours'; a window
that saw nothing usable contributes nothing; and no rule about which
planes must be present is needed.

The truth below is constant over the page, so nothing here depends on
the prior's bandwidth: what is being asked is whether the DECOMPOSITION
is right, not how well the smoother interpolates.

2026-10-12 (CMY-RECEIVER-PLAN A5): the gauge follows the ink the pose is
fit from, read off the row's word as its proxy (`lib/field_gauge`,
CMY-DESIGN R7).  cmy8's word is C and M, read on luma, the gauge above;
cmy's word is C alone, read on R, so the pose IS C's, `F_C` is zero by
name, C's rows inform only the window nuisances and M and Y are free,
each measured from C (CMY-DESIGN R7).
"""

from __future__ import annotations

import numpy as np
import pytest

from holo.receiver.format import identity
from holo.receiver.lib import evidence, field_gauge, plane_field
from holo.receiver.plugins import words
from holo.receiver.tests import test_h3_plane_fields as fx
from holo.receiver.tests.test_h3_field_evidence import rows
from holo.receiver.tests.test_h3_field_lifecycle import prior

#: the review's own numbers (F1), in printed dots along page x
TRUTH_DOTS = (0.6, -0.6, 1.5)
#: the tiles both windows stand over: one 2x2 block of the fixture page
BLOCK = (0, 1, fx.TILES_YX[1], fx.TILES_YX[1] + 1)
#: what a solved field may differ from the injected truth by: the
#: design's own noise scale (§2.4), against which the visibility swing
#: this module refutes is 4.8x
TOLERANCE_DOTS = plane_field.FIELD_NOISE_DOTS
#: item 12's injected pose error and common shift, in dots.  Both are
#: MUCH larger than the tolerance on purpose: at the review's own 0.4 an
#: estimator that put 60 % of the error into the fields and 40 % into the
#: nuisance passed both assertions, so the test tolerated most of the
#: leak it exists to forbid.  At 1.2 dots a leak of one fifth fails.
POSE_ERROR_XY = (1.2, -0.9)
COMMON_SHIFT_XY = (1.5, 1.1)


def _window_rows(window: int, planes: tuple[int, ...], *,
                 weight: float = 1.0,
                 pose_error_xy: tuple[float, float] = (0.0, 0.0),
                 truth_dots: tuple[float, ...] = TRUTH_DOTS,
                 ) -> evidence.Rows:
    """One window's raw measurements of the tiles it stands over.

    Raw is the point: what a window measures is the plane's own
    displacement PLUS that window's pose error, and nothing takes the
    second term off before the solve sees it.
    """
    parts = []
    for plane in planes:
        delta = [[truth_dots[plane] + pose_error_xy[0], pose_error_xy[1]]
                 for _code in BLOCK]
        parts.append(rows(delta, plane=plane, tile_code=list(BLOCK),
                          weight=weight, window=window))
    return evidence.Rows.concat(*parts)


def _solve(*parts: evidence.Rows,
           word: tuple[int, ...] = field_gauge.CM_WORD_PLANES) -> object:
    return plane_field.solve(
        evidence.Rows.concat(*parts), fx.TILES_YX, cell_dots=fx.CELL_DOTS,
        prior=prior(fx.CELL_DOTS), word=word)


def _block_values(solution: object, plane: int, axis: int = 0) -> np.ndarray:
    grid = np.asarray(solution.delta_dots_xy)[plane, ..., axis]
    return np.asarray([grid.reshape(-1)[code] for code in BLOCK])


# --------------------------------------------------------------------
# 11. the frame does not move with what a window happened to see
# --------------------------------------------------------------------

@pytest.mark.parametrize("seen", [(0, 2), (1, 2), (0, 1, 2)])
@pytest.mark.parametrize("weight", [0.25, 1.0, 4.0])
def test_the_y_field_is_the_same_whatever_word_ink_a_window_saw(seen,
                                                                weight):
    """Review F1: measurement quality was defining the coordinates.

    One window sees the whole page and pins the frame.  A second stands
    over the same tiles and sees a subset, at a weight that ranges over
    16x — visibility and confidence, the two things the old gauge let
    into the definition of zero.  Y's field is a property of the printed
    page and may not move by either.
    """
    solution = _solve(_window_rows(0, (0, 1, 2)),
                      _window_rows(1, seen, weight=weight))
    assert _block_values(solution, 2) == pytest.approx(
        TRUTH_DOTS[2], abs=TOLERANCE_DOTS)


def test_the_word_planes_cancel_each_other_at_every_tile():
    """R-A's gauge, stated as the estimator's own arithmetic: the C and
    M fields are equal and opposite everywhere, which is what "the pose
    sits between C and M" means once it is applied to the FIELDS and not
    to each window's row set."""
    solution = _solve(_window_rows(0, (0, 1, 2)))
    grid = np.asarray(solution.delta_dots_xy)
    assert np.allclose(grid[0] + grid[1], 0.0, atol=1e-9)
    assert _block_values(solution, 0) == pytest.approx(
        TRUTH_DOTS[0], abs=TOLERANCE_DOTS)


def test_a_window_that_saw_only_yellow_still_helps():
    """R-A's promise for the scrap with no live word ink: its SHAPE is
    evidence even though its own zero is unknown, and the rule that
    refused it outright (W7 R1) is retired with the per-window gauge it
    belonged to."""
    alone = _solve(_window_rows(0, (0, 1, 2)))
    joined = _solve(_window_rows(0, (0, 1, 2)),
                    _window_rows(1, (2,), weight=4.0))
    assert _block_values(joined, 2) == pytest.approx(
        TRUTH_DOTS[2], abs=TOLERANCE_DOTS)
    assert np.asarray(joined.n_observations).sum() > np.asarray(
        alone.n_observations).sum()


# --------------------------------------------------------------------
# 12. a window's own error lands in its nuisance
# --------------------------------------------------------------------

def test_a_windows_pose_error_appears_in_its_nuisance_and_in_no_field():
    """The estimation model, in one test: what one window's three planes
    share is that window's pose error, and the page's field is what is
    left.  The nuisance is diagnostic state — the pose row stays the only
    owner of a pose — so it may not leak into a published plane."""
    error = POSE_ERROR_XY
    clean = _solve(_window_rows(0, (0, 1, 2)), _window_rows(1, (0, 1, 2)))
    tilted = _solve(_window_rows(0, (0, 1, 2)),
                    _window_rows(1, (0, 1, 2), pose_error_xy=error))
    assert np.allclose(np.asarray(tilted.delta_dots_xy),
                       np.asarray(clean.delta_dots_xy),
                       atol=TOLERANCE_DOTS)
    nuisance = np.asarray(tilted.nuisance_dots_xy)
    assert nuisance[1] == pytest.approx(error, abs=TOLERANCE_DOTS)
    assert nuisance[0] == pytest.approx((0.0, 0.0), abs=TOLERANCE_DOTS)


def test_a_shift_common_to_every_window_is_absorbed_entirely():
    """The degenerate direction, named: a translation applied to every
    plane of every window is a pose error by construction — no pair of
    fields obeying the gauge can express it — so all of it goes to the
    nuisances and none of it to the page."""
    shift = COMMON_SHIFT_XY
    clean = _solve(_window_rows(0, (0, 1, 2)), _window_rows(1, (0, 1, 2)))
    shifted = _solve(
        _window_rows(0, (0, 1, 2), pose_error_xy=shift),
        _window_rows(1, (0, 1, 2), pose_error_xy=shift))
    assert np.allclose(np.asarray(shifted.delta_dots_xy),
                       np.asarray(clean.delta_dots_xy),
                       atol=TOLERANCE_DOTS)
    for window in (0, 1):
        assert np.asarray(shifted.nuisance_dots_xy)[window] == pytest.approx(
            shift, abs=TOLERANCE_DOTS)


# --------------------------------------------------------------------
# A5. the gauge follows the pose's ink, the row's word its proxy
# --------------------------------------------------------------------

#: e043c B1's measured x offsets from C (CMY-RECEIVER-PLAN §0): a cmy page
#: whose pose is C's, so C reads zero and M and Y read these
CMY_TRUTH_DOTS = (0.0, 1.23, 1.06)
CMY_WORD = (0,)


@pytest.mark.parametrize("format_ref, word, column, coefficient", [
    ("c3-cmy8-r0550@10x10", (0, 1), (0, 0, 1), (1.0, -1.0, 1.0)),
    ("c3-cmy7@10x10", (0, 1), (0, 0, 1), (1.0, -1.0, 1.0)),
    ("c3-cmy-r0850@10x10", CMY_WORD, (0, 0, 1), (0.0, 1.0, 1.0)),
])
def test_the_gauge_is_the_rows_word_ink(format_ref, word, column,
                                        coefficient):
    """cmy8's and cmy7's derived table is the one the solve hard-wired
    before A5 (C +1 and M -1 on field 0, Y +1 on field 1); cmy's C has no
    field and M and Y are the two.  The word proxies the pose's ink: a
    row addressed on R reads its word '1' as the one dark state there."""
    row = identity.resolve_format_ref(format_ref)
    assert field_gauge.word_planes(row.word_states[1]) == word
    assert (words.ADDRESSING_DARK[row.family] == {row.word_states[1]}) == (
        row.family in words.ADDRESSING_ON_R)
    field_column, field_coefficient = field_gauge.gauge_table(word)
    assert tuple(field_column.tolist()) == column
    assert tuple(field_coefficient.tolist()) == coefficient


def test_under_cmys_gauge_c_is_zero_and_m_and_y_are_measured_from_c():
    """R7: every window's three planes share its pose error, C's rows pin
    it, and what M and Y measure beyond it is their displacement from C;
    C's own field is exactly zero and has no uncertainty to report."""
    solution = _solve(
        _window_rows(0, (0, 1, 2), pose_error_xy=POSE_ERROR_XY,
                     truth_dots=CMY_TRUTH_DOTS),
        _window_rows(1, (0, 1, 2), pose_error_xy=COMMON_SHIFT_XY,
                     truth_dots=CMY_TRUTH_DOTS),
        word=CMY_WORD)
    grid = np.asarray(solution.delta_dots_xy)
    assert not np.any(grid[0])
    assert not np.any(np.asarray(solution.uncertainty_dots)[0])
    for plane in (1, 2):
        assert _block_values(solution, plane) == pytest.approx(
            CMY_TRUTH_DOTS[plane], abs=TOLERANCE_DOTS)
    nuisance = np.asarray(solution.nuisance_dots_xy)
    assert nuisance[0] == pytest.approx(POSE_ERROR_XY, abs=TOLERANCE_DOTS)
    assert nuisance[1] == pytest.approx(COMMON_SHIFT_XY, abs=TOLERANCE_DOTS)


def test_a_cmy_window_that_saw_only_cyan_moves_no_field():
    """C's coefficient is zero: a window whose rows are all C fits its own
    translation exactly and leaves the page where it was."""
    alone = _solve(_window_rows(0, (0, 1, 2), truth_dots=CMY_TRUTH_DOTS),
                   word=CMY_WORD)
    joined = _solve(_window_rows(0, (0, 1, 2), truth_dots=CMY_TRUTH_DOTS),
                    _window_rows(1, (0,), pose_error_xy=POSE_ERROR_XY,
                                 truth_dots=CMY_TRUTH_DOTS),
                    word=CMY_WORD)
    assert np.allclose(np.asarray(joined.delta_dots_xy),
                       np.asarray(alone.delta_dots_xy), atol=1e-12)
    assert np.asarray(joined.nuisance_dots_xy)[1] == pytest.approx(
        POSE_ERROR_XY, abs=1e-9)


@pytest.mark.parametrize("word, seen, known", [
    ((0, 1), (2,), (False, False, True)),
    ((0, 1), (1,), (True, True, False)),
    (CMY_WORD, (2,), (True, False, True)),
    (CMY_WORD, (1,), (True, True, False)),
])
def test_a_plane_the_gauge_holds_at_the_pose_is_known_by_name(word, seen,
                                                              known):
    """I13 under each gauge: planes reading one field stand together, and
    cmy's C is known without a measurement — zero is its definition."""
    solution = _solve(_window_rows(0, seen, truth_dots=CMY_TRUTH_DOTS),
                      word=word)
    assert tuple(np.asarray(solution.plane_known).tolist()) == known

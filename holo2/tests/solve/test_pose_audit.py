"""The placement decision kernel, pinned where its arithmetic is fragile.

W0 sub-wave A2 (H4-PLAN §3-W0).  ``pose_audit`` is a port of the
score/audit/refine/harvest half of v1's ``placement/search.py``, and R4
pins it BEHAVIOURALLY — so what is asserted here is the arithmetic a
"cleanup" would silently change:

* the scorer's float32 reduction (a float64 promotion is a different
  number, and this file says which number),
* the frozen E022 parity split, in both of its two spellings,
* the straddle audit's ``int(np.ceil(cut))`` edge, chosen at a cut where
  ceil, round-half-to-even, and truncation all disagree,
* ``local_search``'s ``(-soft_z, origin_y, origin_x)`` order, ties and
  ``-inf`` included,
* ``predict_from_anchor``'s ``int(round(...))``, on exact halves either
  side of zero,
* the harvest's row shape, its python-scalar dtypes, and its silent skip
  of pilot sites that are not BCH word sites.

The cross-tree comparison against ``src/holo`` itself is W0's scratch
differential (``scratch/w0a2/differential.py``, 698 comparisons over a
clean and a banded fixture); the firewall keeps it out of this tree.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pytest

from holo2.format import pilots
from holo2.solve.place_model import (E022_SUPPORT_FLOOR_SITES,
                                     HISTORICAL_E022_GATE, AffinePose,
                                     AttemptBudget, CandidateScore,
                                     PlacementConfig, PoseSegment, PoseWindow)
from holo2.solve.pose_audit import (WHOLE_WORD_PARITY, ScoreMemo,
                                    audit_segment, fragment_reference_sites,
                                    local_search, observations_for_segment,
                                    parity_mask, predict_from_anchor,
                                    refine_patch_pose)


# ------------------------------------------------------------- hand fixtures

@dataclass(frozen=True)
class _Page:
    values: np.ndarray
    sites: np.ndarray


class _Field:
    """The two arrays this kernel reads off a reference-field provider."""

    def __init__(self, values: np.ndarray, sites: np.ndarray) -> None:
        self._page = _Page(np.asarray(values, np.uint8),
                           np.asarray(sites, bool))
        self.pages_asked: list[int] = []

    def page(self, page: int) -> _Page:
        self.pages_asked.append(int(page))
        return self._page


@dataclass(frozen=True)
class _Sample:
    """The members ``audit_segment``/``observations_for_segment`` read."""

    bits: np.ndarray
    evidence: np.ndarray


@dataclass(frozen=True)
class _Patch:
    """The three arrays ``local_search`` hands to the memo."""

    evidence: np.ndarray
    bits: np.ndarray
    mask: np.ndarray


def _field_from(cells: dict[tuple[int, int], int],
                shape: tuple[int, int] = (6, 6)) -> _Field:
    """A page whose sites are exactly ``cells``, carrying those values."""
    values = np.zeros(shape, np.uint8)
    sites = np.zeros(shape, bool)
    for (y, x), value in cells.items():
        values[y, x] = value
        sites[y, x] = True
    return _Field(values, sites)


def _budget(max_hypotheses: int = 2401) -> AttemptBudget:
    return AttemptBudget(max_hypotheses, 1e-3, 0.08, "test/route",
                         gate=HISTORICAL_E022_GATE)


# ----------------------------------------------------------- the parity split

def test_parity_mask_is_the_frozen_e022_split() -> None:
    """``(131*y + 17*x) & 1``, both coefficients odd, so ``(y + x) & 1``."""
    mask = parity_mask((3, 4), (0, 0), 0)
    assert mask.dtype == np.bool_ and mask.shape == (3, 4)
    assert mask.tolist() == [
        [True, False, True, False],
        [False, True, False, True],
        [True, False, True, False],
    ]
    # Parity 1 is the exact complement, cell for cell.
    assert (parity_mask((3, 4), (0, 0), 1) == ~mask).all()
    # An odd origin translates the split by one cell in that axis.
    assert (parity_mask((3, 4), (1, 0), 0) == ~mask).all()
    assert (parity_mask((3, 4), (0, 1), 0) == ~mask).all()
    assert (parity_mask((3, 4), (1, 1), 0) == mask).all()


def test_parity_mask_agrees_with_the_absolute_coefficient_form() -> None:
    """The mask form and the ``131/17`` form are the same partition."""
    for origin in ((0, 0), (3, 5), (12, 7), (101, 44)):
        y0, x0 = origin
        mask = parity_mask((5, 7), origin, 0)
        for y in range(5):
            for x in range(7):
                absolute = ((y0 + y) * 131 + (x0 + x) * 17) & 1
                assert bool(mask[y, x]) is (absolute == 0)


# ---------------------------------------------------------------- the scorer

def test_parity_score_returns_the_exact_weighted_mismatch() -> None:
    """Four sites, all binary-exact, so the whole tuple is a literal."""
    field = _field_from({(0, 0): 0, (0, 2): 1, (1, 1): 0, (3, 3): 1})
    evidence = np.zeros((6, 6), np.float32)
    for cell, value in (((0, 0), 0.5), ((0, 2), -0.25),
                        ((1, 1), 0.75), ((3, 3), -1.0)):
        evidence[cell] = value
    bits = np.zeros((6, 6), np.uint8)
    bits[0, 2] = 1
    bits[3, 3] = 1
    mask = np.ones((6, 6), bool)
    memo = ScoreMemo(field)
    score = memo.parity_score(0, evidence, bits, mask, 0, (0, 0), 0,
                              WHOLE_WORD_PARITY)
    # expected_sign = (+1, -1, +1, -1); the products are all positive, so
    # correlation == total_weight == 2.5 and the mismatch is exactly zero.
    assert score == (0.0, 0, 4, float(2.5 / np.sqrt(2.5)))


def test_parity_score_prices_a_sign_disagreement() -> None:
    field = _field_from({(0, 0): 0, (0, 2): 1, (1, 1): 0, (3, 3): 1})
    evidence = np.zeros((6, 6), np.float32)
    for cell, value in (((0, 0), 0.5), ((0, 2), -0.25),
                        ((1, 1), 0.75), ((3, 3), 1.0)):
        evidence[cell] = value
    bits = np.zeros((6, 6), np.uint8)
    bits[0, 2] = 1
    mask = np.ones((6, 6), bool)
    memo = ScoreMemo(field)
    mismatch, errors, support, soft_z = memo.parity_score(
        0, evidence, bits, mask, 0, (0, 0), 0, WHOLE_WORD_PARITY)
    # correlation = 0.5 + 0.25 + 0.75 - 1.0 = 0.5; total weight 2.5.
    assert mismatch == (2.5 - 0.5) / (2.0 * 2.5) == 0.4
    assert soft_z == float(0.5 / np.sqrt(2.5))
    assert (errors, support) == (1, 4)      # only (3, 3) reads wrong


def test_parity_score_reduces_in_float32_not_float64() -> None:
    """The per-call ``np.float32`` cast IS the number, not a detail.

    Every site carries the same float64 evidence, chosen so that its
    float32 image differs; the sums then differ in the last bits.  The
    scorer must report the float32 one — and the two must actually differ,
    or this test would pass on a float64 port too.
    """
    cells = {(y, x): (y + x) % 2 for y in range(6) for x in range(6)}
    field = _field_from(cells)
    raw = 0.12345678901234567
    evidence = np.full((6, 6), raw, np.float64)
    for (y, x), value in cells.items():
        if value:
            evidence[y, x] = -raw
    bits = np.array([[cells[(y, x)] for x in range(6)] for y in range(6)],
                    np.uint8)
    mask = np.ones((6, 6), bool)
    memo = ScoreMemo(field)
    _, _, support, soft_z = memo.parity_score(
        0, evidence, bits, mask, 0, (0, 0), 0, WHOLE_WORD_PARITY)
    assert support == 36

    def _z(dtype: type) -> float:
        selected = np.asarray(evidence, dtype).ravel()
        sign = 1.0 - 2.0 * np.asarray(
            [cells[(y, x)] for y in range(6) for x in range(6)],
            np.uint8).astype(dtype)
        correlation = float(np.sum(sign * selected))
        weight = float(np.abs(selected).sum())
        return float(correlation / np.sqrt(max(weight, 1e-9)))

    assert _z(np.float32) != _z(np.float64)     # the pin has teeth
    assert soft_z == _z(np.float32)


def test_parity_score_splits_the_two_disjoint_populations() -> None:
    """Parity 0 and 1 partition the sites; the sentinel scores both."""
    cells = {(y, x): 0 for y in range(6) for x in range(6)}
    field = _field_from(cells)
    evidence = np.full((6, 6), 0.5, np.float32)
    bits = np.zeros((6, 6), np.uint8)
    mask = np.ones((6, 6), bool)
    memo = ScoreMemo(field)
    search = memo.parity_score(0, evidence, bits, mask, 0, (0, 0), 0, 0)
    validation = memo.parity_score(0, evidence, bits, mask, 0, (0, 0), 0, 1)
    whole = memo.parity_score(0, evidence, bits, mask, 0, (0, 0), 0,
                              WHOLE_WORD_PARITY)
    assert (search[2], validation[2], whole[2]) == (18, 18, 36)


def test_parity_score_refuses_without_overlap_or_support() -> None:
    field = _field_from({(0, 0): 0})
    evidence = np.zeros((6, 6), np.float32)
    bits = np.zeros((6, 6), np.uint8)
    memo = ScoreMemo(field)
    # The three probes carry three DIFFERENT sample keys on purpose: the
    # memo key names the sample, not the arrays, so a caller that reuses a
    # key for a different evidence/mask pair is asking for the cached
    # answer (the key is the caller's declaration — see ScoreMemo).
    off_page = memo.parity_score(0, evidence, bits, np.ones((6, 6), bool),
                                 0, (-99, -99), 0, WHOLE_WORD_PARITY)
    assert off_page == (1.0, 0, 0, float("-inf"))
    masked_out = memo.parity_score(1, evidence, bits, np.zeros((6, 6), bool),
                                   0, (0, 0), 0, WHOLE_WORD_PARITY)
    assert masked_out == (1.0, 0, 0, float("-inf"))
    # Supported, but every weight is zero: mismatch falls back to 1.0.
    zero_weight = memo.parity_score(2, evidence, bits, np.ones((6, 6), bool),
                                    0, (0, 0), 0, WHOLE_WORD_PARITY)
    assert zero_weight == (1.0, 0, 1, 0.0)


def test_the_memo_is_keyed_on_the_whole_probe_and_owned_by_its_caller() -> None:
    field = _field_from({(0, 0): 0, (1, 1): 1})
    evidence = np.full((6, 6), 0.5, np.float32)
    bits = np.zeros((6, 6), np.uint8)
    mask = np.ones((6, 6), bool)
    memo = ScoreMemo(field)
    probe = (0, evidence, bits, mask, 0, (0, 0), 0, WHOLE_WORD_PARITY)
    first = memo.parity_score(*probe)
    assert (memo.requests, memo.hits) == (1, 0)
    assert memo.parity_score(*probe) == first
    assert (memo.requests, memo.hits) == (2, 1)
    # rot_k is taken mod 4 in the key, so 4 is 0's hit.
    memo.parity_score(0, evidence, bits, mask, 0, (0, 0), 4,
                      WHOLE_WORD_PARITY)
    assert (memo.requests, memo.hits) == (3, 2)
    # A different sample key is a different probe, never a hit.
    memo.parity_score(1, evidence, bits, mask, 0, (0, 0), 0,
                      WHOLE_WORD_PARITY)
    assert (memo.requests, memo.hits) == (4, 2)
    # Nothing is shared between memos: a fresh one starts cold.
    assert (ScoreMemo(field).requests, ScoreMemo(field).hits) == (0, 0)


def test_candidate_applies_the_four_coupled_bars() -> None:
    """Both floors and both mismatch bars, with the gate's exact strictness."""
    cells = {(y, x): 0 for y in range(6) for x in range(6)}
    field = _field_from(cells)
    evidence = np.full((6, 6), 0.5, np.float32)
    bits = np.zeros((6, 6), np.uint8)
    mask = np.ones((6, 6), bool)
    memo = ScoreMemo(field)
    scored = memo.candidate(0, evidence, bits, mask, 0, (0, 0), 0,
                            _budget(), "chain")
    assert isinstance(scored, CandidateScore)
    assert (scored.search_mismatch, scored.validation_mismatch) == (0.0, 0.0)
    # 18 sites per parity is under the derived floor, so a perfect read
    # still fails: the floor is a SUPPORT bar, not a quality bar.
    assert scored.search_support == 18 < _budget().min_support
    assert scored.passes is False
    assert (scored.page, scored.origin_yx, scored.rot_k) == (0, (0, 0), 0)
    assert scored.route == "chain"


# ----------------------------------------------------- the chain route's law

class _FixedMemo:
    """A memo that answers from a table: pins ORDER without pinning scores."""

    def __init__(self, soft_z: dict[tuple[int, int], float]) -> None:
        self.soft_z = soft_z

    def candidate(self, _key: int, _evidence: np.ndarray, _bits: np.ndarray,
                  _mask: np.ndarray, page: int, origin_yx: tuple[int, int],
                  rot_k: int, _budget: AttemptBudget,
                  route: str) -> CandidateScore:
        z = self.soft_z.get(origin_yx, -1.0)
        return CandidateScore(page, origin_yx, rot_k, 0.0, 0.0, 0, 0,
                              99, 99, z, True, route)


def _patch() -> _Patch:
    zeros = np.zeros((4, 4), np.float32)
    return _Patch(zeros, np.zeros((4, 4), np.uint8), np.ones((4, 4), bool))


def test_local_search_orders_by_soft_z_then_origin() -> None:
    """``(-soft_z, origin_y, origin_x)``: ties break north-then-west."""
    config = replace(PlacementConfig(), neighbor_radius_cells=1)
    # Every neighbour ties at 5.0 except one clear winner south-east.
    table = {(y, x): 5.0 for y in range(9, 12) for x in range(19, 22)}
    table[(11, 21)] = 9.0
    outcome = local_search(_patch(), 0, 0, (10, 20), _budget(),
                           _FixedMemo(table), sample_key=0,  # type: ignore[arg-type]
                           config=config)
    assert outcome.best is not None
    assert outcome.best.origin_yx == (11, 21)
    assert [row.origin_yx for row in outcome.runner_ups] == [
        (9, 19), (9, 20), (9, 21),
        (10, 19), (10, 20), (10, 21),
        (11, 19), (11, 20),
    ]
    # The winner sits 1 cell from the prediction, inside consistency_cells.
    assert outcome.predicted_origin_yx == (10, 20)
    assert outcome.predicted_residual_cells == 1.0
    assert outcome.accepted is True and outcome.reason == "accepted"
    assert outcome.hypotheses == 9


def test_local_search_refuses_a_winner_outside_the_consistency_radius() -> None:
    config = replace(PlacementConfig(), neighbor_radius_cells=3,
                     consistency_cells=2)
    table = {(13, 23): 9.0}
    outcome = local_search(_patch(), 0, 0, (10, 20), _budget(),
                           _FixedMemo(table), sample_key=0,  # type: ignore[arg-type]
                           config=config)
    assert outcome.best is not None and outcome.best.origin_yx == (13, 23)
    assert outcome.predicted_residual_cells == 3.0
    assert outcome.accepted is False
    assert outcome.reason == "local_validation_failed"


def test_local_search_refuses_an_unscorable_neighbourhood() -> None:
    config = replace(PlacementConfig(), neighbor_radius_cells=1)
    table = {(y, x): float("-inf") for y in range(9, 12)
             for x in range(19, 22)}
    outcome = local_search(_patch(), 0, 0, (10, 20), _budget(),
                           _FixedMemo(table), sample_key=0,  # type: ignore[arg-type]
                           config=config)
    assert outcome.best is None and outcome.reason == "insufficient_support"
    # Even unscorable, the full neighbourhood is reported in order.
    assert len(outcome.runner_ups) == 9
    assert [row.origin_yx for row in outcome.runner_ups][:2] == [
        (9, 19), (9, 20)]


def test_local_search_refuses_before_searching_an_over_budget_domain() -> None:
    config = replace(PlacementConfig(), neighbor_radius_cells=3)
    outcome = local_search(_patch(), 0, 0, (10, 20), _budget(48),
                           _FixedMemo({}), sample_key=0,  # type: ignore[arg-type]
                           config=config)
    assert outcome.reason == "attempt_budget_exceeded"
    assert outcome.hypotheses == 49 and outcome.best is None
    assert outcome.support_floor == _budget(48).min_support


# ------------------------------------------------------- the affine transport

def _pose(origin: tuple[float, float]) -> AffinePose:
    return AffinePose(origin, ((2.0, 0.0), (0.0, 2.0)), (0.0, 0.0), 2.0, 0.0)


@pytest.mark.parametrize(
    "delta_pixels,expected",
    [
        ((4.0, 6.0), (2, 3)),          # integral: no rounding at all
        ((1.0, 3.0), (0, 2)),          # +0.5 -> 0, +1.5 -> 2  (to even)
        ((5.0, 7.0), (2, 4)),          # +2.5 -> 2, +3.5 -> 4  (to even)
        ((-1.0, -3.0), (0, -2)),       # -0.5 -> 0, -1.5 -> -2 (to even)
        ((-5.0, -7.0), (-2, -4)),      # -2.5 -> -2, -3.5 -> -4
        ((1.2, 2.8), (1, 1)),          # 0.6 -> 1, 1.4 -> 1: ordinary
    ],
)
def test_predict_from_anchor_rounds_half_to_even(
    delta_pixels: tuple[float, float], expected: tuple[int, int]
) -> None:
    """``int(round(...))`` on a float64 — numpy's half-to-EVEN, not half-up.

    ``rot_k=0`` makes both rotation translations zero and the anchor origin
    the zero cell, so the prediction IS the rounded cell delta.
    """
    anchor = _pose((100.0, 200.0))
    target = _pose((100.0 + delta_pixels[0], 200.0 + delta_pixels[1]))
    predicted = predict_from_anchor(anchor, (48, 64), (0, 0), 0,
                                    target, (32, 40))
    assert predicted == expected
    assert all(type(value) is int for value in predicted)


def test_predict_from_anchor_carries_the_rot90_translations() -> None:
    """Each quarter turn moves the origin by the two shape translations."""
    anchor = _pose((100.0, 200.0))
    target = _pose((100.0 + 4.0, 200.0 + 6.0))          # (2, 3) cells
    assert predict_from_anchor(anchor, (48, 64), (7, 11), 0,
                               target, (32, 40)) == (9, 14)
    # rot_k=1: S=[[0,-1],[1,0]] -> (-3, 2); anchor t=(63, 0), target t=(39, 0).
    assert predict_from_anchor(anchor, (48, 64), (7, 11), 1,
                               target, (32, 40)) == (28, 13)
    # rot_k=2: S=-I -> (-2, -3); anchor t=(47, 63), target t=(31, 39).
    assert predict_from_anchor(anchor, (48, 64), (7, 11), 2,
                               target, (32, 40)) == (21, 32)
    # rot_k=3: S=[[0,1],[-1,0]] -> (3, -2); anchor t=(0, 47), target t=(0, 31).
    assert predict_from_anchor(anchor, (48, 64), (7, 11), 3,
                               target, (32, 40)) == (10, 25)


# -------------------------------------------------------- the correspondence

def test_fragment_reference_sites_inverts_the_rotation_in_order() -> None:
    """Local points, expected bits, and page points stay corresponding."""
    field = _field_from({(1, 1): 1, (1, 3): 0, (3, 1): 0, (4, 4): 1})
    mask = np.ones((6, 6), bool)
    for rot_k in range(4):
        points, expected, absolute = fragment_reference_sites(
            mask, field, 0, (0, 0), rot_k)
        assert points.dtype == np.int64 and absolute.dtype == np.int64
        assert expected.dtype == np.uint8
        assert points.shape == (4, 2) and absolute.shape == (4, 2)
        # Local points are in raster order of the UNROTATED window, and
        # each one still names the page cell whose value came back.
        assert points.tolist() == sorted(points.tolist())
        for local, page_point, value in zip(points, absolute, expected,
                                            strict=True):
            assert field.page(0).values[tuple(page_point)] == value
            assert field.page(0).sites[tuple(page_point)]
        if rot_k == 0:
            assert (points == absolute).all()


def test_fragment_reference_sites_clips_an_overhanging_window() -> None:
    field = _field_from({(0, 0): 1, (5, 5): 0})
    mask = np.ones((6, 6), bool)
    points, expected, absolute = fragment_reference_sites(
        mask, field, 0, (3, 3), 0)
    assert absolute.tolist() == [[5, 5]]
    assert points.tolist() == [[2, 2]] and expected.tolist() == [0]
    empty_points, empty_expected, empty_absolute = fragment_reference_sites(
        mask, field, 0, (-99, -99), 0)
    assert empty_points.shape == (0, 2) and empty_absolute.shape == (0, 2)
    assert empty_expected.shape == (0,)


# ---------------------------------------------------------------- the audit

def _audit_fixture(bad_from_row: int, *, shape: tuple[int, int] = (20, 8),
                   rows: tuple[int, ...] | None = None
                   ) -> tuple[_Sample, _Field, np.ndarray]:
    """Every cell is a site; rows at/after ``bad_from_row`` read wrong."""
    height, width = shape
    values = np.zeros(shape, np.uint8)
    sites = np.zeros(shape, bool)
    for y in (range(height) if rows is None else rows):
        sites[y, :] = True
    read = values.copy()
    read[bad_from_row:, :] ^= 1
    field = _Field(values, sites)
    sample = _Sample(read, np.zeros(shape, np.float32))
    return sample, field, np.ones(shape, bool)


def test_audit_cuts_on_the_ceiling_of_the_change_point() -> None:
    """cut = 12.5: ceil is 13, round-half-to-even is 12, truncation is 12.

    So row 12 — the last clean row — must survive, and row 13 must not.
    A port that reached for ``np.rint`` or ``int()`` loses row 12's sites.
    """
    config = replace(PlacementConfig(), audit_min_sites=4)
    sample, field, core = _audit_fixture(13)
    good, refused, kept, residual = audit_segment(
        sample, core, field, 0, (0, 0), 0, config, min_support=1)
    assert good[12].all() and not good[13].any()
    assert kept == 13 * 8 and residual == 0.0 and refused is False


def test_audit_cuts_the_other_side_when_the_bad_band_is_low() -> None:
    """Same edge, mirrored: rows 0..12 wrong cuts at ceil(12.5) = 13."""
    config = replace(PlacementConfig(), audit_min_sites=4)
    height, width = 20, 8
    values = np.zeros((height, width), np.uint8)
    read = values.copy()
    read[:13, :] ^= 1
    sample = _Sample(read, np.zeros((height, width), np.float32))
    field = _Field(values, np.ones((height, width), bool))
    good, refused, kept, residual = audit_segment(
        sample, np.ones((height, width), bool), field, 0, (0, 0), 0, config,
        min_support=1)
    assert not good[12].any() and good[13].all()
    assert kept == 7 * 8 and residual == 0.0 and refused is False


def test_audit_midpoint_is_the_mean_of_the_two_straddled_coordinates() -> None:
    """With a coordinate gap the cut is integral and ceil changes nothing."""
    config = replace(PlacementConfig(), audit_min_sites=4)
    present = tuple(range(0, 12)) + tuple(range(16, 28))
    sample, field, core = _audit_fixture(16, shape=(28, 8), rows=present)
    good, _refused, _kept, residual = audit_segment(
        sample, core, field, 0, (0, 0), 0, config, min_support=1)
    # 0.5 * (11 + 16) = 13.5 -> ceil 14, so rows 14 and 15 (siteless) go too.
    assert good[13].all() and not good[14].any()
    assert residual == 0.0


def test_audit_leaves_a_clean_window_whole() -> None:
    config = replace(PlacementConfig(), audit_min_sites=4)
    sample, field, core = _audit_fixture(20)          # nothing is wrong
    good, refused, kept, residual = audit_segment(
        sample, core, field, 0, (0, 0), 0, config, min_support=1)
    assert good.all() and kept == 160
    assert residual == 0.0 and refused is False


def test_audit_refuses_below_the_population_floor() -> None:
    """Each parity population is floored SEPARATELY, after the cut."""
    config = replace(PlacementConfig(), audit_min_sites=4)
    sample, field, core = _audit_fixture(13)
    # The cut keeps rows 0..12 of eight cells: 104 sites, 52 per parity.
    _good, refused, kept, _residual = audit_segment(
        sample, core, field, 0, (0, 0), 0, config, min_support=52)
    assert kept == 104 and refused is False           # exactly at the floor
    _good, refused, _kept, _residual = audit_segment(
        sample, core, field, 0, (0, 0), 0, config, min_support=53)
    assert refused is True                            # one site short
    # 104 sites would clear a floor of 104 if the populations were pooled;
    # they are not, so a floor of 53 already refuses.
    _good, refused, _kept, _residual = audit_segment(
        sample, core, field, 0, (0, 0), 0, config, min_support=104)
    assert refused is True


def test_audit_refuses_above_the_post_bar() -> None:
    """A residual the cuts could not reach still refuses the window."""
    config = replace(PlacementConfig(), audit_min_sites=4)
    height, width = 20, 8
    values = np.zeros((height, width), np.uint8)
    read = values.copy()
    read[:, ::2] ^= 1                # half wrong, evenly spread: no cut helps
    sample = _Sample(read, np.zeros((height, width), np.float32))
    field = _Field(values, np.ones((height, width), bool))
    good, refused, kept, residual = audit_segment(
        sample, np.ones((height, width), bool), field, 0, (0, 0), 0, config,
        min_support=1)
    assert good.all() and kept == 160
    assert residual == 0.5 > config.audit_post_bar and refused is True


def test_audit_short_circuits_below_twice_the_minimum_site_count() -> None:
    """Too few correspondences to split: the core comes back untouched."""
    config = PlacementConfig()                         # audit_min_sites = 15
    sample, field, _core = _audit_fixture(13)
    core = np.zeros((20, 8), bool)
    core[:3, :] = True                                 # 24 < 2 * 15
    good, refused, kept, residual = audit_segment(
        sample, core, field, 0, (0, 0), 0, config, min_support=1)
    assert (good == core).all() and kept == 24 and residual == 0.0
    assert refused is False


@pytest.mark.parametrize("floor", [0, -1, True, 1.0, "30"])
def test_audit_refuses_a_floor_that_is_not_a_positive_integer(
    floor: object,
) -> None:
    sample, field, core = _audit_fixture(13)
    with pytest.raises(ValueError):
        audit_segment(sample, core, field, 0, (0, 0), 0, PlacementConfig(),
                      min_support=floor)  # type: ignore[arg-type]


def test_audit_default_floor_is_the_e022_measured_datum() -> None:
    """The default is A1's carried row, not a literal repeated here."""
    config = replace(PlacementConfig(), audit_min_sites=4)
    sample, field, core = _audit_fixture(13)
    default = audit_segment(sample, core, field, 0, (0, 0), 0, config)
    explicit = audit_segment(sample, core, field, 0, (0, 0), 0, config,
                             min_support=E022_SUPPORT_FLOOR_SITES)
    assert default[1:] == explicit[1:]


# --------------------------------------------------------------- the harvest

def _one_tile_field(seed: bytes) -> tuple[_Field, np.ndarray]:
    """A single 64-cell tile carrying the row's real word-site lattice."""
    word_cells = pilots.word_site_cells_yx(seed)
    values = np.zeros((64, 64), np.uint8)
    sites = np.zeros((64, 64), bool)
    sites[word_cells[:, 0], word_cells[:, 1]] = True
    values[word_cells[:, 0], word_cells[:, 1]] = (
        np.arange(word_cells.shape[0], dtype=np.uint8) & 1)
    return _Field(values, sites), word_cells


def test_observations_harvest_shape_and_dtypes() -> None:
    seed = bytes(range(16))
    field, word_cells = _one_tile_field(seed)
    bits = np.zeros((64, 64), np.uint8)
    bits[word_cells[:, 0], word_cells[:, 1]] = 1
    evidence = np.zeros((64, 64), np.float32)
    evidence[word_cells[:, 0], word_cells[:, 1]] = 0.25
    sample = _Sample(bits, evidence)
    rows = observations_for_segment(
        sample, np.ones((64, 64), bool), field, 0, (0, 0), 0,
        capture_id="cap-A", family_seed=seed)
    assert len(rows) == pilots.N_WORD_SITES
    assert {row.site_index for row in rows} == set(
        range(pilots.N_WORD_SITES))
    for row in rows:
        assert type(row.page) is int and row.page == 0
        assert row.tile_yx == (0, 0)
        assert type(row.tile_yx[0]) is int
        assert type(row.site_index) is int
        assert type(row.bit) is int and row.bit == 1
        assert type(row.evidence) is float and row.evidence == 0.25
        assert row.capture_id == "cap-A"


def test_observations_skip_sites_that_are_not_word_sites() -> None:
    """Filler labels ride Lane C but are not BCH word observations."""
    seed = bytes(range(16))
    field, word_cells = _one_tile_field(seed)
    occupied = {(int(y), int(x)) for y, x in word_cells}
    spare = next((y, x) for y in range(64) for x in range(64)
                 if (y, x) not in occupied)
    field.page(0).sites[spare] = True
    sample = _Sample(np.zeros((64, 64), np.uint8),
                     np.zeros((64, 64), np.float32))
    rows = observations_for_segment(
        sample, np.ones((64, 64), bool), field, 0, (0, 0), 0,
        capture_id="cap-A", family_seed=seed)
    assert len(rows) == pilots.N_WORD_SITES        # the spare produced none


def test_observations_name_the_tile_the_page_cell_falls_in() -> None:
    seed = bytes(range(16))
    field, word_cells = _one_tile_field(seed)
    sample = _Sample(np.zeros((64, 64), np.uint8),
                     np.zeros((64, 64), np.float32))
    # Place the window one whole tile down and two across.
    rows = observations_for_segment(
        sample, np.ones((64, 64), bool), field, 0, (64, 128), 0,
        capture_id="cap-A", family_seed=seed)
    assert rows == ()                              # nothing overlaps a site
    big_values = np.zeros((192, 256), np.uint8)
    big_sites = np.zeros((192, 256), bool)
    big_sites[64 + word_cells[:, 0], 128 + word_cells[:, 1]] = True
    rows = observations_for_segment(
        sample, np.ones((64, 64), bool), _Field(big_values, big_sites), 0,
        (64, 128), 0, capture_id="cap-B", family_seed=seed)
    assert len(rows) == pilots.N_WORD_SITES
    assert {row.tile_yx for row in rows} == {(1, 2)}


def test_observations_of_an_empty_core_are_empty() -> None:
    seed = bytes(range(16))
    field, _word_cells = _one_tile_field(seed)
    sample = _Sample(np.zeros((64, 64), np.uint8),
                     np.zeros((64, 64), np.float32))
    assert observations_for_segment(
        sample, np.zeros((64, 64), bool), field, 0, (0, 0), 0,
        capture_id="cap-A", family_seed=seed) == ()


# ------------------------------------------------------------ the refinement

@dataclass(frozen=True)
class _Context:
    """The four members ``refine_patch_pose`` reads off a region crop."""

    y0: int
    x0: int
    filtered: np.ndarray
    backing: float


@dataclass(frozen=True)
class _RefineSample:
    segment: PoseSegment
    means: np.ndarray
    mask: np.ndarray
    bits: np.ndarray
    evidence: np.ndarray


@dataclass(frozen=True)
class _RefinePatch:
    sample: _RefineSample
    mask: np.ndarray


class _Resampler:
    """Records the segment it was asked to re-read; returns what it is told."""

    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[PoseSegment] = []

    def __call__(self, _context: object, segment: PoseSegment) -> object:
        self.calls.append(segment)
        return self.result


CELLS, PITCH_PX, PAD = 20, 4.0, 10


def _refine_fixture() -> tuple[_Context, _RefinePatch, _Field]:
    """A crop whose site contrast peaks at exactly the fitted pose.

    Each cell's evidence is ONE pixel wide, so an ``order=1`` read at any
    sub-cell offset loses contrast: the refinement's train margin has a
    strict maximum at zero angle and zero phase.
    """
    values = np.fromfunction(
        lambda y, x: ((y * 3 + x * 5) % 7 < 3).astype(np.uint8),
        (CELLS, CELLS), dtype=np.int64)
    field = _Field(values, np.ones((CELLS, CELLS), bool))
    span = int(PITCH_PX * CELLS) + 2 * PAD
    filtered = np.full((span, span), 0.86, np.float32)
    for i in range(CELLS):
        for j in range(CELLS):
            level = 0.20 if values[i, j] else 0.95
            filtered[int(PITCH_PX * i) + PAD, int(PITCH_PX * j) + PAD] = level
    context = _Context(400, 300, filtered, 0.9)
    pose = AffinePose(
        (context.y0 + float(PAD), context.x0 + float(PAD)),
        ((PITCH_PX, 0.0), (0.0, PITCH_PX)), (0.0, 0.0), PITCH_PX, 0.0)
    window = PoseWindow(0, 0, (PAD, PAD), (CELLS, CELLS), 0, CELLS * CELLS)
    segment = PoseSegment(window, pose, CELLS * CELLS, 1.0,
                          (PITCH_PX, PITCH_PX), 0.0)
    means = filtered[PAD::int(PITCH_PX), PAD::int(PITCH_PX)][:CELLS, :CELLS]
    mask = np.ones((CELLS, CELLS), bool)
    sample = _RefineSample(segment, means.copy(), mask,
                           (means < 0.86).astype(np.uint8),
                           np.zeros((CELLS, CELLS), np.float32))
    return context, _RefinePatch(sample, mask), field


def test_refine_finds_the_pose_it_was_already_at() -> None:
    context, patch, field = _refine_fixture()
    resampler = _Resampler("the-resampled-window")
    outcome = refine_patch_pose(
        context, patch, field, 0, (0, 0), 0, PlacementConfig(),
        resample=resampler)  # type: ignore[arg-type]
    assert outcome is not None
    assert abs(outcome.delta_angle_deg) <= 1e-9
    assert outcome.delta_phase_yx == (0.0, 0.0)
    assert outcome.heldout_before == outcome.heldout_after == 0.0
    # The window is re-read exactly once, through the refined segment.
    assert len(resampler.calls) == 1
    refined_pose = resampler.calls[0].pose
    base_pose = patch.sample.segment.pose
    assert refined_pose.origin_yx == base_pose.origin_yx
    assert np.allclose(refined_pose.matrix(), base_pose.matrix())
    assert refined_pose.phase_yx == base_pose.phase_yx
    assert refined_pose.pitch_px == pytest.approx(PITCH_PX)
    assert outcome.sample == "the-resampled-window"


def test_refine_is_off_when_the_policy_says_so() -> None:
    context, patch, field = _refine_fixture()
    resampler = _Resampler("unused")
    assert refine_patch_pose(
        context, patch, field, 0, (0, 0), 0,
        replace(PlacementConfig(), refine=False),
        resample=resampler) is None  # type: ignore[arg-type]
    assert resampler.calls == []


def test_refine_declines_a_window_the_sampler_cannot_re_read() -> None:
    """A ``None`` re-read is a declined refinement, not a half-adopted pose."""
    context, patch, field = _refine_fixture()
    resampler = _Resampler(None)
    assert refine_patch_pose(
        context, patch, field, 0, (0, 0), 0, PlacementConfig(),
        resample=resampler) is None  # type: ignore[arg-type]
    assert len(resampler.calls) == 1


def test_refine_declines_below_the_site_and_parity_floors() -> None:
    context, patch, field = _refine_fixture()
    resampler = _Resampler("unused")
    # No overlap at all: no correspondences, so nothing to optimise.
    assert refine_patch_pose(
        context, patch, field, 0, (-99, -99), 0, PlacementConfig(),
        resample=resampler) is None  # type: ignore[arg-type]
    # Overlapping, but fewer than refine_min_total_sites correspondences.
    assert refine_patch_pose(
        context, patch, field, 0, (CELLS - 5, CELLS - 5), 0,
        PlacementConfig(), resample=resampler) is None  # type: ignore[arg-type]
    # Enough sites overall, but one parity population is too thin.
    thin = replace(PlacementConfig(), refine_min_total_sites=4,
                   refine_min_sites_per_parity=2)
    single_row = _RefinePatch(
        replace(patch.sample, mask=np.zeros((CELLS, CELLS), bool)),
        patch.mask)
    single_row.sample.mask[0, 0:8:2] = True          # four cells, one parity
    assert refine_patch_pose(
        context, single_row, field, 0, (0, 0), 0, thin,
        resample=resampler) is None  # type: ignore[arg-type]
    assert resampler.calls == []

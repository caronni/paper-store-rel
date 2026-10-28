"""PK3 (P1): the CMY7 calibration head.

The head is a seven-parameter post-transform of one region's CMY7 relative
scores, fitted by a hand-rolled damped Newton.  Four things have to be
true and each gets its own pin here:

1. THE OPTIMIZER IS RIGHT.  A convex problem has one answer, so the
   Newton is differentiated against a deliberately dumb, deliberately slow
   optimizer written inline below — a dense grid over the scale crossed
   with bisection coordinate descent over the offsets, which uses only the
   SIGN of a one-dimensional derivative and shares no code with the
   implementation.
2. IT IS DETERMINISTIC.  Same inputs, same seven numbers, every time.
3. EVERY REFUSAL IS REACHABLE, and a leak between the fitting and gating
   populations (or back into the QDA's own training rows) RAISES.
4. NO HEAD IS A LITERAL NULL.  With ``cmy7_head is None`` the emitted
   evidence is byte-identical to the pre-P1 expression (risk R2), and
   ``HOLO_COLOR_STACK_FORCE_NULL`` never even attempts a fit.

The end-to-end pins run the real ``collect_color_evidence`` on rendered
cmy7 fields: one channel carrying the pathology P1 exists to fix (cells
knocked off their class hard enough that a Gaussian QDA is confidently
wrong about them), and one clean channel where the honest answer is to
change nothing.
"""
from __future__ import annotations

import numpy as np
import pytest

from _color_stack_fixtures import build_fixture, build_head_fixture
from holo.receive import color_detect, color_payload, color_stack
from holo.receive.color_calibration import (
    HEAD_MIN_SEARCH_PER_STATE,
    HEAD_MIN_VALIDATION,
    HEAD_MIN_VALIDATION_PER_STATE,
    HEAD_N_OFFSETS,
    HEAD_SCALE_MAX,
    HEAD_SCALE_MIN,
    Cmy7Head,
    Cmy7HeadError,
    _mean_nll,
    _refused,
    class_balanced_weights,
    fit_cmy7_head,
    head_sub_split,
)
from holo.receive.color_fitting import (
    CMY7_RELATIVE_SCORE_BOUND,
    _DetectorFit,
)
from holo.receive.color_payload import collect_color_evidence

# The pathological channel: light blur and almost no pixel noise, but 6%
# of CELLS knocked off their class by 0.30 in scan units.  A Gaussian QDA
# models the pixel noise perfectly and the outliers not at all, so it is
# CONFIDENTLY WRONG exactly where it is wrong — the corpus fact (19% of
# cells at the bound, wrong cells at median |score| 18.8/20).
PATHOLOGICAL = (1.0, 0.02, 0.0, 0.06, 0.30)
# The honest channel: nothing to fix, so the validation gate must refuse.
CLEAN = (0.5, 0.004)


# ---------------------------------------------------------------- helpers

def _synthetic(seed: int, n: int = 700, scale: float = 0.35,
               spread: float = 3.0) -> tuple[np.ndarray, np.ndarray,
                                             np.ndarray]:
    """A small labelled score set with a known head baked in.

    Labels are DRAWN from the head's own distribution, so the NLL surface
    is a realistic one rather than a separable toy.  Seeded: a call is a
    pure function of ``seed``.
    """
    rng = np.random.default_rng(seed)
    scores = rng.normal(0.0, spread, (n, HEAD_N_OFFSETS))
    offsets = rng.normal(0.0, 0.6, HEAD_N_OFFSETS)
    logits = np.concatenate(
        (np.zeros((n, 1)), scale * scores + offsets), axis=1)
    probabilities = np.exp(logits - logits.max(axis=1, keepdims=True))
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    states = np.array(
        [rng.choice(HEAD_N_OFFSETS + 1, p=row) for row in probabilities],
        np.int64)
    return scores, states, offsets


def _keys(n: int, *, page: int = 0, start: int = 0) -> np.ndarray:
    """Canonical (page, y, x) site keys on one row of a page."""
    return np.stack((
        np.full(n, page, np.int64),
        np.arange(start, start + n, dtype=np.int64) // 64,
        np.arange(start, start + n, dtype=np.int64) % 64,
    ), axis=1)


def _balanced_keys(states: np.ndarray) -> np.ndarray:
    """Site keys whose ``&2`` sub-split puts every state on BOTH sides.

    On row ``y = 0`` the sub-split hash is ``17x``, and ``17 == 1 (mod 4)``,
    so ``x mod 4 in {0,1}`` lands on cal_search and ``{2,3}`` on
    cal_validation.  Alternating a per-state counter across those two
    residues gives every state both sides with distinct keys, which is
    what the floors need before any of them can be exercised on purpose.
    """
    keys = np.zeros((states.size, 3), np.int64)
    seen: dict[int, int] = {}
    for index, state in enumerate(states.tolist()):
        ordinal = seen.get(state, 0)
        seen[state] = ordinal + 1
        keys[index, 2] = 4 * index + 2 * (ordinal & 1)
    return keys


# ------------------------------------------- the trusted slow optimizer

def _offset_derivative(scores: np.ndarray, states: np.ndarray,
                       weights: np.ndarray, scale: float,
                       offsets: np.ndarray, index: int) -> float:
    """d(weighted NLL)/d(b_index) — used only through its SIGN."""
    logits = scale * scores + offsets
    shift = np.maximum(0.0, logits.max(axis=1))
    exponentials = np.exp(logits - shift[:, None])
    partition = np.exp(-shift) + exponentials.sum(axis=1)
    probability = exponentials[:, index] / partition
    indicator = (states == index + 1).astype(np.float64)
    return float(np.sum(weights * (probability - indicator)))


def _bisect_offset(scores: np.ndarray, states: np.ndarray,
                   weights: np.ndarray, scale: float, offsets: np.ndarray,
                   index: int, steps: int = 44) -> float:
    """Solve the 1-D convex subproblem by bisection on the derivative."""
    low, high = -60.0, 60.0
    trial = offsets.copy()
    for _step in range(steps):
        middle = 0.5 * (low + high)
        trial[index] = middle
        if _offset_derivative(
                scores, states, weights, scale, trial, index) > 0.0:
            high = middle
        else:
            low = middle
    return 0.5 * (low + high)


def _grid_search(scores: np.ndarray, states: np.ndarray,
                 weights: np.ndarray, grid: np.ndarray, sweeps: int,
                 ) -> tuple[float, float, np.ndarray]:
    best: tuple[float, float, np.ndarray] | None = None
    for scale in grid.tolist():
        offsets = np.zeros(HEAD_N_OFFSETS, np.float64)
        for _sweep in range(sweeps):
            for index in range(HEAD_N_OFFSETS):
                offsets[index] = _bisect_offset(
                    scores, states, weights, scale, offsets, index)
        loss = _mean_nll(scores, states, scale, offsets, weights)
        if best is None or loss < best[0]:
            best = (loss, scale, offsets.copy())
    assert best is not None
    return best


def _slow_fit(scores: np.ndarray, states: np.ndarray, weights: np.ndarray,
              grid: np.ndarray, sweeps: int = 8,
              ) -> tuple[float, float, np.ndarray]:
    """Dense scale grid x bisection coordinate descent on the offsets.

    Deliberately dumb and deliberately slow.  It shares no line of code
    with the damped Newton under test and uses only derivative SIGNS, so
    agreement between the two is real evidence rather than a tautology.
    MEASURED: eight sweeps rank scales correctly but leave the offsets
    ~3e-5 short of converged, so this scan is the COARSE half of the
    differential; the sharp half runs many sweeps at a single scale.
    """
    return _grid_search(scores, states, weights, grid, sweeps)


def _converged_offsets(scores: np.ndarray, states: np.ndarray,
                       weights: np.ndarray, scale: float,
                       sweeps: int = 40) -> np.ndarray:
    """Bisection coordinate descent run to convergence at one scale.

    MEASURED at 40 sweeps on this fixture family: reproduces the damped
    Newton's own objective value to the last bit.
    """
    offsets = np.zeros(HEAD_N_OFFSETS, np.float64)
    for _sweep in range(sweeps):
        for index in range(HEAD_N_OFFSETS):
            offsets[index] = _bisect_offset(
                scores, states, weights, scale, offsets, index)
    return offsets


# ------------------------------------------------------------- the pins

def test_newton_matches_a_dense_grid_and_coordinate_search() -> None:
    scores, states, _truth = _synthetic(0xC0FFEE)
    keys = _balanced_keys(states)
    fit = fit_cmy7_head(
        scores, states, keys, qda_search_site_keys=np.zeros((0, 3), np.int64))
    assert fit.head is not None, fit.reason

    search = head_sub_split(keys)
    weights = class_balanced_weights(states[search])
    grid = np.geomspace(HEAD_SCALE_MIN, HEAD_SCALE_MAX, 41)
    slow_loss, slow_scale, slow_offsets = _slow_fit(
        scores[search], states[search], weights, grid)
    newton_loss = _mean_nll(
        scores[search], states[search], fit.head.scale, fit.head.offsets,
        weights)

    # (a) COARSE half — no scale on the whole box does better, and the
    # search's own best scale lands inside one grid step of the Newton's.
    assert newton_loss <= slow_loss + 1e-12
    # The coarse scan's OWN resolution bounds this: a ~19% scale step and
    # eight coordinate sweeps.  Precision is the sharp half's job.
    assert slow_loss - newton_loss < 1e-3
    step = float(grid[1] / grid[0])
    assert 1.0 / step <= fit.head.scale / slow_scale <= step
    assert np.max(np.abs(fit.head.offsets - slow_offsets)) < 0.05

    # (b) SHARP half — at the Newton's own scale, a fully converged
    # bisection coordinate descent reproduces its offsets and its
    # objective to the last bits.  Nothing here shares code with the
    # implementation: only the SIGN of a one-dimensional derivative.
    converged = _converged_offsets(
        scores[search], states[search], weights, fit.head.scale)
    converged_loss = _mean_nll(
        scores[search], states[search], fit.head.scale, converged, weights)
    assert abs(converged_loss - newton_loss) < 1e-9
    assert np.max(np.abs(fit.head.offsets - converged)) < 1e-5


@pytest.mark.parametrize("seed", (1, 20260807, 0xBEEF))
def test_newton_finds_a_stationary_point(seed: int) -> None:
    """A convex minimum has a vanishing (projected) gradient."""
    from holo.receive.color_calibration import (
        _objective,
        _projected_gradient_norm,
    )

    scores, states, _truth = _synthetic(seed)
    keys = _balanced_keys(states)
    fit = fit_cmy7_head(
        scores, states, keys, qda_search_site_keys=np.zeros((0, 3), np.int64))
    assert fit.head is not None, fit.reason
    search = head_sub_split(keys)
    weights = class_balanced_weights(states[search])
    _value, gradient, _hessian = _objective(
        scores[search], states[search], fit.head.scale, fit.head.offsets,
        weights)
    assert _projected_gradient_norm(fit.head.scale, gradient) < 1e-6


def test_repeated_fits_are_identical() -> None:
    scores, states, _truth = _synthetic(7)
    keys = _balanced_keys(states)
    empty = np.zeros((0, 3), np.int64)
    first = fit_cmy7_head(scores, states, keys, qda_search_site_keys=empty)
    second = fit_cmy7_head(scores, states, keys, qda_search_site_keys=empty)
    assert first.head is not None and second.head is not None
    assert first.head.scale == second.head.scale
    assert np.array_equal(first.head.offsets, second.head.offsets)
    assert first.iterations == second.iterations
    assert (first.identity_validation_nll, first.candidate_validation_nll) \
        == (second.identity_validation_nll, second.candidate_validation_nll)


def test_hessian_is_positive_semidefinite() -> None:
    """Convexity, checked where it matters: at and away from the optimum."""
    from holo.receive.color_calibration import _objective

    scores, states, _truth = _synthetic(11)
    weights = class_balanced_weights(states)
    for scale, offsets in (
        (1.0, np.zeros(HEAD_N_OFFSETS)),
        (0.2, np.linspace(-1.0, 1.0, HEAD_N_OFFSETS)),
        (5.0, np.full(HEAD_N_OFFSETS, -0.7)),
    ):
        _value, _gradient, hessian = _objective(
            scores, states, scale, np.asarray(offsets, np.float64), weights)
        assert np.allclose(hessian, hessian.T)
        assert np.min(np.linalg.eigvalsh(hessian)) > -1e-12


# --------------------------------------------------------- the head form

def test_head_clips_the_scale_to_the_registered_box() -> None:
    offsets = np.zeros(HEAD_N_OFFSETS)
    assert Cmy7Head(1e-9, offsets).scale == HEAD_SCALE_MIN
    assert Cmy7Head(1e9, offsets).scale == HEAD_SCALE_MAX
    assert Cmy7Head(0.5, offsets).scale == 0.5
    with pytest.raises(Cmy7HeadError):
        Cmy7Head(float("nan"), offsets)
    with pytest.raises(Cmy7HeadError):
        Cmy7Head(1.0, np.zeros(5))
    with pytest.raises(Cmy7HeadError):
        Cmy7Head(1.0, np.full(HEAD_N_OFFSETS, np.inf))


def test_head_apply_is_pure_affine_and_leaves_w_at_zero() -> None:
    head = Cmy7Head(0.4, np.arange(HEAD_N_OFFSETS, dtype=np.float64))
    scores = np.arange(12, dtype=np.float64).reshape(2, HEAD_N_OFFSETS)
    original = scores.copy()
    applied = head.apply(scores)
    assert np.array_equal(scores, original)
    assert np.allclose(applied, 0.4 * original + head.offsets)
    # W is the fixed 0 reference and has no parameter: an all-zero score
    # row moves only by the offsets, never by the scale.
    assert np.allclose(
        head.apply(np.zeros((1, HEAD_N_OFFSETS))), head.offsets)
    assert head.temperature == pytest.approx(1.0 / 0.4)
    assert not head.offsets.flags.writeable
    with pytest.raises(Cmy7HeadError):
        head.apply(np.zeros((2, 3)))


def test_sub_split_is_the_next_bit_of_the_standing_hash_family() -> None:
    """`&1` is the QDA split, `&2` is P1's, `&4` is reserved for P9."""
    keys = _keys(4096)
    hashed = 131 * keys[:, 1] + 17 * keys[:, 2]
    assert np.array_equal(head_sub_split(keys), (hashed & 2) == 0)
    # It is a genuine second axis: knowing the QDA side tells you nothing
    # about the head side (all four combinations occur, near-evenly).
    qda = (hashed & 1) == 0
    head = head_sub_split(keys)
    for left in (False, True):
        for right in (False, True):
            assert np.count_nonzero((qda == left) & (head == right)) > 900


# ----------------------------------------------------- refusals and leaks

def test_search_class_starvation_is_reachable() -> None:
    scores, states, _truth = _synthetic(3, n=400)
    # Erase one state from the fitting side only.
    keys = _balanced_keys(states)
    search = head_sub_split(keys)
    victims = np.flatnonzero(search & (states == 4))
    keep = victims[HEAD_MIN_SEARCH_PER_STATE - 1:]
    states = states.copy()
    states[keep] = 0
    fit = fit_cmy7_head(
        scores, states, keys, qda_search_site_keys=np.zeros((0, 3), np.int64))
    assert fit.reason == "search_class_starved"
    assert fit.head is None and not fit.adopted
    assert fit.search_class_counts[4] < HEAD_MIN_SEARCH_PER_STATE


def test_heldout_starvation_is_reachable_by_total_and_by_state() -> None:
    empty = np.zeros((0, 3), np.int64)
    # (a) too few validation rows overall
    scores, states, _truth = _synthetic(5, n=900)
    keys = _balanced_keys(states)
    validation = ~head_sub_split(keys)
    drop = np.flatnonzero(validation)[HEAD_MIN_VALIDATION - 1:]
    subset = np.ones(states.size, bool)
    subset[drop] = False
    fit = fit_cmy7_head(
        scores[subset], states[subset], keys[subset],
        qda_search_site_keys=empty)
    assert fit.reason == "heldout_starved"
    assert fit.n_validation < HEAD_MIN_VALIDATION

    # (b) plenty of rows, but one state below the per-state floor
    scores, states, _truth = _synthetic(6, n=600)
    keys = _balanced_keys(states)
    validation = ~head_sub_split(keys)
    states = states.copy()
    victims = np.flatnonzero(validation & (states == 2))
    states[victims[HEAD_MIN_VALIDATION_PER_STATE - 1:]] = 0
    fit = fit_cmy7_head(
        scores, states, keys, qda_search_site_keys=empty)
    assert fit.reason == "heldout_starved"
    assert fit.n_validation >= HEAD_MIN_VALIDATION
    assert fit.validation_class_counts[2] < HEAD_MIN_VALIDATION_PER_STATE


def test_validation_gate_refuses_a_head_that_does_not_help() -> None:
    """Scores that already ARE calibrated logits leave nothing to gain."""
    rng = np.random.default_rng(0x5A11)
    n = 2000
    logits = rng.normal(0.0, 1.2, (n, HEAD_N_OFFSETS))
    full = np.concatenate((np.zeros((n, 1)), logits), axis=1)
    probabilities = np.exp(full - full.max(axis=1, keepdims=True))
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    states = np.array(
        [rng.choice(HEAD_N_OFFSETS + 1, p=row) for row in probabilities],
        np.int64)
    fit = fit_cmy7_head(
        logits, states, _balanced_keys(states),
        qda_search_site_keys=np.zeros((0, 3), np.int64))
    if fit.adopted:
        # Allowed only as a hair's-width improvement at a ~ 1.
        assert fit.head is not None
        assert abs(fit.head.scale - 1.0) < 0.25
        assert (fit.identity_validation_nll
                - fit.candidate_validation_nll) < 0.05
    else:
        assert fit.reason == "validation_gate_failed"
        assert fit.head is None


def test_a_repeated_cal_site_raises() -> None:
    """The falsifiable form of the SEARCH/VALIDATION leak.

    The sub-split is a pure function of the site key, so no cell can land
    on both sides by construction — the way this leak can ACTUALLY happen
    is an upstream deduplication failure that puts one observation in the
    population twice.  That is what raises.
    """
    scores, states, _truth = _synthetic(9)
    keys = _balanced_keys(states).copy()
    keys[5] = keys[4]
    with pytest.raises(Cmy7HeadError, match="repeat a cell"):
        fit_cmy7_head(scores, states, keys,
                      qda_search_site_keys=np.zeros((0, 3), np.int64))


def test_the_intersection_check_itself_detects_an_overlap() -> None:
    """The kept mirror of `detect.fit_calibration`'s contract, unit-tested.

    `fit_cmy7_head` still runs the literal cal_search ∩ cal_validation
    intersection even though the split makes it structurally empty; this
    pins that the predicate it runs is a real one, not a stub that always
    says "disjoint".
    """
    from holo.receive.color_calibration import _rows_overlap

    left = np.array([[0, 1, 2], [0, 3, 4]], np.int64)
    right = np.array([[0, 5, 6], [0, 3, 4]], np.int64)
    assert _rows_overlap(left, right)
    assert not _rows_overlap(left, np.array([[0, 5, 6]], np.int64))
    assert not _rows_overlap(left, np.zeros((0, 3), np.int64))
    assert not _rows_overlap(np.zeros((0, 3), np.int64), right)
    # A near miss on one coordinate is not an overlap.
    assert not _rows_overlap(left, np.array([[1, 3, 4]], np.int64))


def test_leak_back_into_the_qda_training_rows_raises() -> None:
    scores, states, _truth = _synthetic(10)
    keys = _balanced_keys(states)
    search = np.flatnonzero(head_sub_split(keys))
    validation = np.flatnonzero(~head_sub_split(keys))
    with pytest.raises(Cmy7HeadError, match="cal SEARCH overlaps"):
        fit_cmy7_head(scores, states, keys,
                      qda_search_site_keys=keys[search[:1]])
    with pytest.raises(Cmy7HeadError, match="cal VALIDATION overlaps"):
        fit_cmy7_head(scores, states, keys,
                      qda_search_site_keys=keys[validation[:1]])


def test_malformed_populations_raise() -> None:
    scores, states, _truth = _synthetic(12)
    keys = _balanced_keys(states)
    empty = np.zeros((0, 3), np.int64)
    with pytest.raises(Cmy7HeadError, match="shape \\(N,6\\)"):
        fit_cmy7_head(scores[:, :3], states, keys, qda_search_site_keys=empty)
    with pytest.raises(Cmy7HeadError, match="align"):
        fit_cmy7_head(scores, states[:-1], keys, qda_search_site_keys=empty)
    with pytest.raises(Cmy7HeadError, match="shape \\(N,3\\)"):
        fit_cmy7_head(scores, states, keys[:, :2], qda_search_site_keys=empty)
    with pytest.raises(Cmy7HeadError, match="seven-state"):
        fit_cmy7_head(scores, states + 7, keys, qda_search_site_keys=empty)
    with pytest.raises(Cmy7HeadError, match="finite"):
        broken = scores.copy()
        broken[0, 0] = np.nan
        fit_cmy7_head(broken, states, keys, qda_search_site_keys=empty)


# ---------------------------------------------- the class-balancing law

def test_the_head_calibrates_instead_of_re_priorizing() -> None:
    """The measured PK3 defect, pinned.

    The CMY7 QDA is equal-prior by construction while its known-furniture
    fit population is not (MEASURED on the 8x8 cmy7 field: 45% W, 39% one
    dust state, against a ~1/7-each payload field).  An UNWEIGHTED
    multinomial NLL fits that furniture prior straight into the offsets and
    degrades payload evidence.  This pins that the fitted offsets carry no
    such prior — reweighting the population's class mix must not move the
    head.
    """
    scores, states, _truth = _synthetic(0xBA1, n=900)
    keys = _balanced_keys(states)
    empty = np.zeros((0, 3), np.int64)
    balanced = fit_cmy7_head(
        scores, states, keys, qda_search_site_keys=empty)
    assert balanced.head is not None

    # Duplicate every W row four times: an unweighted objective would
    # shift each offset by about log(1/4) = -1.39; a class-balanced one
    # must not move at all.
    repeat = np.where(states == 0, 4, 1)
    order = np.repeat(np.arange(states.size), repeat)
    skewed = fit_cmy7_head(
        scores[order], states[order], _balanced_keys(states[order]),
        qda_search_site_keys=empty)
    assert skewed.head is not None
    assert abs(skewed.head.scale - balanced.head.scale) < 0.05
    assert np.max(np.abs(skewed.head.offsets - balanced.head.offsets)) < 0.25


def test_class_balanced_weights_equalize_represented_states() -> None:
    states = np.array([0, 0, 0, 0, 1, 2, 2, 6], np.int64)
    weights = class_balanced_weights(states)
    assert weights.mean() == pytest.approx(1.0)
    totals = np.bincount(states, weights=weights, minlength=7)
    represented = np.bincount(states, minlength=7) > 0
    assert np.allclose(totals[represented], totals[represented][0])
    assert np.allclose(totals[~represented], 0.0)
    # A balanced population reproduces the unweighted objective exactly.
    balanced = np.array([0, 1, 2, 3, 4, 5, 6], np.int64)
    assert np.array_equal(
        class_balanced_weights(balanced), np.ones(7, np.float64))


# ------------------------------------------------------ R2: the null path

def _cmy7_fit(fixture):
    """Capture one region's real selection, features and stack result."""
    captured: list = []
    original = color_stack.fit_region_stack

    def recording(spec, selection, rows, arms, residuals, **kwargs):
        # PK4.1: the ladder consumes ``arms``, so a recorder keeps what it
        # needs BEFORE the call (color_stack's memory-ownership note).
        base = arms.base
        result = original(
            spec, selection, rows, arms, residuals, **kwargs)
        captured.append((selection, base, result))
        return result

    color_payload.fit_region_stack = recording
    try:
        collect_color_evidence(
            fixture.raster, fixture.source, fixture.address, fixture.spec)
    finally:
        color_payload.fit_region_stack = original
    return captured[0]


def test_evidence_with_no_head_is_the_literal_pre_p1_expression() -> None:
    """R2: ``cmy7_head is None`` must not reorder a single float op."""
    fixture = build_fixture("cmy7-clean")
    _selection, base, result = _cmy7_fit(fixture)
    fit = result.selected_fit
    assert fit is not None and fit.detector is None
    features = np.asarray(base[0], np.float64)

    # The pre-P1 body, transcribed from color_fitting.py at 0f13972.
    scores = color_detect.cmy7_relative_scores(fit.model, features)
    divisor = np.maximum(
        1.0,
        np.max(np.abs(scores), axis=1, keepdims=True)
        / CMY7_RELATIVE_SCORE_BOUND,
    )
    expected = scores / divisor

    headless = _DetectorFit(
        fit.model, None, fit.heldout_loss, fit.word_heldout_loss,
        fit.dust_heldout_loss, fit.n_train, fit.n_heldout, fit.class_counts)
    assert headless.cmy7_head is None
    got = headless.evidence(features)
    assert got.dtype == expected.dtype
    assert np.array_equal(got.view(np.uint8), expected.view(np.uint8))
    # ...and the divisor-returning twin is the same array, bit for bit.
    twin, reported = headless.evidence_with_divisor(features)
    assert np.array_equal(twin.view(np.uint8), expected.view(np.uint8))
    assert np.array_equal(reported, divisor)


def test_head_applies_before_the_bound_and_the_bound_still_holds() -> None:
    fixture = build_fixture("cmy7-clean")
    _selection, base, result = _cmy7_fit(fixture)
    fit = result.selected_fit
    assert fit is not None
    features = np.asarray(base[0], np.float64)
    head = Cmy7Head(0.05, np.linspace(-0.4, 0.4, HEAD_N_OFFSETS))
    from dataclasses import replace

    calibrated = replace(fit, cmy7_head=head)
    values, divisor = calibrated.evidence_with_divisor(features)

    scores = head.apply(
        color_detect.cmy7_relative_scores(fit.model, features))
    expected_divisor = np.maximum(
        1.0,
        np.max(np.abs(scores), axis=1, keepdims=True)
        / CMY7_RELATIVE_SCORE_BOUND)
    assert np.array_equal(divisor, expected_divisor)
    assert np.array_equal(values, scores / expected_divisor)
    # `cmy7linf20` stays truthful: the bound applies AFTER calibration.
    assert np.max(np.abs(values)) <= CMY7_RELATIVE_SCORE_BOUND + 1e-9
    # Cooling moves every cell toward the bound rather than past it: no
    # cell's divisor grows, and the region's worst one shrinks by about
    # the scale.  (Whether that clears the bound is a channel question —
    # the end-to-end pins measure the fraction that actually does.)
    _raw, raw_divisor = fit.evidence_with_divisor(features)
    assert np.all(divisor <= raw_divisor)
    assert np.max(divisor) < np.max(raw_divisor)
    assert np.count_nonzero(divisor > 1.0) <= np.count_nonzero(
        raw_divisor > 1.0)


# ------------------------------------------------------ the force-null law

def test_force_null_never_attempts_a_head_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def spy(*args, **kwargs):
        calls["n"] += 1
        raise AssertionError("force-null must not fit a head")

    monkeypatch.setattr(color_stack, "fit_cmy7_head", spy)
    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    fixture = build_head_fixture(*PATHOLOGICAL)
    evidence = collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec)
    assert calls["n"] == 0
    region = evidence.regions[0]
    assert region.cmy7_head_reason == color_stack.FORCE_NULL_REASON
    assert not region.cmy7_head_adopted
    assert region.cmy7_head_temperature == 1.0
    # The canary is still MEASURED under force-null — that is what makes
    # the harness differential a before/after rather than a before/blank.
    assert region.cmy7_saturation_fraction > 0.0
    # PK3.1: the floor never ran, so its input is UNMEASURED, not 0.0 —
    # force-null must not pay for a gate it never consults.
    assert (region.cmy7_baseline_saturation_fraction
            == color_stack.HEAD_SATURATION_UNMEASURED)


@pytest.mark.parametrize(
    "value,expected",
    (("", False), ("0", False), ("false", False), ("no", False),
     ("off", False), ("1", True), ("true", True), ("yes", True)),
)
def test_force_null_reads_the_environment_at_call_time(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool,
) -> None:
    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, value)
    assert color_stack.force_null_enabled() is expected
    monkeypatch.delenv(color_stack.FORCE_NULL_ENV)
    assert color_stack.force_null_enabled() is False


def test_force_null_evidence_is_byte_identical_to_the_null_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_head_fixture(*CLEAN)
    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    forced = collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec)
    monkeypatch.delenv(color_stack.FORCE_NULL_ENV)
    live = collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec)
    # The clean channel's head refuses, so the two arms must agree bit for
    # bit — the refusal is a NULL, not an identity transform.
    assert live.regions[0].cmy7_head_reason == "validation_gate_failed"
    for left, right in zip(forced.windows, live.windows, strict=True):
        assert np.array_equal(
            np.asarray(left.evidence_values).view(np.uint8),
            np.asarray(right.evidence_values).view(np.uint8))


# ------------------------------------------------------------ end to end

def _payload_quality(fixture, evidence) -> tuple[float, float]:
    """Argmax accuracy and mean NLL of EMITTED evidence at the truth."""
    correct = 0
    total = 0
    loss = 0.0
    for window in evidence.windows:
        cells = np.asarray(window.page_cells_yx, np.int64)
        truth = fixture.field[cells[:, 0], cells[:, 1]].astype(np.int64)
        values = np.asarray(window.evidence_values, np.float64)
        logits = np.concatenate(
            (np.zeros((values.shape[0], 1)), values), axis=1)
        correct += int(np.count_nonzero(logits.argmax(axis=1) == truth))
        total += truth.size
        shift = logits.max(axis=1, keepdims=True)
        partition = shift[:, 0] + np.log(np.exp(logits - shift).sum(axis=1))
        loss += float(np.sum(
            partition - logits[np.arange(truth.size), truth]))
    return correct / total, loss / total


def _refuse_head(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn OFF the head alone, leaving every other arm running.

    PK4 landed arm A3 (per-window photometric maps) BELOW the head, so
    ``HOLO_COLOR_STACK_FORCE_NULL`` is no longer a head-ISOLATING
    differential — it disables the whole ladder, and on a channel where
    A3 adopts the two arms then differ in two places at once.  These
    end-to-end pins are about the head, so the null arm they need is "the
    same ladder, without a head": the fitter returns its ordinary gate
    refusal and every arm above it is bit-for-bit the live arm's.
    """
    monkeypatch.setattr(
        color_stack, "fit_cmy7_head",
        lambda *args, **kwargs: _refused(
            "validation_gate_failed",
            np.zeros(HEAD_N_OFFSETS + 1, np.int64),
            np.zeros(HEAD_N_OFFSETS + 1, np.int64)))


def _both_arms(fixture, monkeypatch: pytest.MonkeyPatch):
    with monkeypatch.context() as without_head:
        _refuse_head(without_head)
        null = collect_color_evidence(
            fixture.raster, fixture.source, fixture.address, fixture.spec)
    live = collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec)
    return null, live


def test_end_to_end_head_adopts_and_moves_the_saturation_canary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_head_fixture(*PATHOLOGICAL)
    null, live = _both_arms(fixture, monkeypatch)
    before, after = null.regions[0], live.regions[0]

    assert after.cmy7_head_adopted and after.cmy7_head_reason == "adopted"
    # The head COOLS an overconfident detector: temperature 1/a > 1.
    assert after.cmy7_head_temperature > 2.0
    # The canary this arm exists to move.
    assert before.cmy7_saturation_fraction > 0.9
    assert after.cmy7_saturation_fraction < 0.5

    # Decode is not worse — measured on the EMITTED evidence against the
    # printed truth, which is what the certification chain consumes.
    null_accuracy, null_loss = _payload_quality(fixture, null)
    live_accuracy, live_loss = _payload_quality(fixture, live)
    assert live_accuracy >= null_accuracy
    assert live_loss < null_loss
    # The arms above the head are untouched by it.
    assert before.registration_adopted == after.registration_adopted
    assert before.selected_heldout_logloss == after.selected_heldout_logloss
    assert before.class_counts == after.class_counts


def test_end_to_end_clean_channel_changes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The validation gate protects a channel with nothing to fix."""
    fixture = build_head_fixture(*CLEAN)
    null, live = _both_arms(fixture, monkeypatch)
    region = live.regions[0]
    if region.cmy7_head_adopted:
        assert abs(region.cmy7_head_temperature - 1.0) < 0.05
    else:
        assert region.cmy7_head_reason == "validation_gate_failed"
    assert (null.regions[0].cmy7_saturation_fraction
            == region.cmy7_saturation_fraction)
    for left, right in zip(null.windows, live.windows, strict=True):
        assert np.array_equal(left.evidence_values, right.evidence_values)


# ----------------------------------------- PK3.1: the saturation floor

def test_the_saturation_floor_constant_is_the_swept_value() -> None:
    """The floor is MEASURED, so the number itself is a pin.

    Swept (COLOR-UPLIFT-MEASUREMENTS §4.5.2) over the twelve measured
    per-lane pre-head saturations of xerox c3-cmy7.  The three below 0.25
    (r00 .117, l00 .131, m00 .221) contributed ZERO of the head's twelve
    gained addresses and FOUR of its five lost ones, while every gain
    came from a lane at >= .455.  The measured distribution therefore has
    one wide empty band, .221 -> .455, and 0.30 is the swept candidate
    deepest inside it (margin .079 below, .155 above) — the other three
    candidates buy the same outcome with a tenth of the margin.  The
    second capture agrees from below (xerox c2-cmy7's coarse lane, .050).
    """
    assert color_stack.HEAD_SATURATION_FLOOR == 0.30
    assert color_stack.HEAD_SATURATION_REASON == "saturation_below_floor"
    assert color_stack.HEAD_SATURATION_UNMEASURED == -1.0
    # The two measured populations the sweep separated, as it saw them.
    no_gain_lanes = (0.117, 0.131, 0.221)
    gaining_lanes = (0.455, 0.497, 0.592, 0.599, 0.608, 0.610, 0.618,
                     0.643, 0.676)
    assert max(no_gain_lanes) < color_stack.HEAD_SATURATION_FLOOR
    assert min(gaining_lanes) > color_stack.HEAD_SATURATION_FLOOR


def test_pre_head_saturation_counts_ignore_an_attached_head() -> None:
    """The floor's input is the PRE-head divisor, by construction."""
    fixture = build_head_fixture(*PATHOLOGICAL)
    _selection, base, result = _cmy7_fit(fixture)
    fit = result.selected_fit
    assert fit is not None and fit.detector is None
    features = np.asarray(base[0], np.float64)

    raw = _DetectorFit(
        fit.model, None, fit.heldout_loss, fit.word_heldout_loss,
        fit.dust_heldout_loss, fit.n_train, fit.n_heldout, fit.class_counts)
    cells, hits = raw.pre_head_saturation_counts(features)
    # It IS the emitted canary's own divisor, counted the same way.
    _values, divisor = raw.evidence_with_divisor(features)
    assert cells == divisor.shape[0]
    assert hits == int(np.count_nonzero(divisor > 1.0))
    # A head that cools by 20x drops the emitted saturation but cannot
    # move the pre-head number by a single cell.
    from dataclasses import replace

    cooled = replace(
        raw, cmy7_head=Cmy7Head(0.05, np.zeros(HEAD_N_OFFSETS)))
    assert cooled.pre_head_saturation_counts(features) == (cells, hits)
    _cooled_values, cooled_divisor = cooled.evidence_with_divisor(features)
    assert int(np.count_nonzero(cooled_divisor > 1.0)) < hits


def test_the_saturation_floor_is_configuration_and_publishes_itself(
) -> None:
    """PK-CLEAN: the swept floor is an ARGUMENT, not an environment read.

    Same contract as before minus the hatch: refused outside [0, 1], and
    the EFFECTIVE value published per region — a swept run must state its
    own number rather than leave the policy token, which names the FROZEN
    one, to be believed.  ``satfloor30`` stays in the token because this
    floor is alive and earning (PK3.1); what changed is only HOW a sweep
    reaches it.
    """
    assert color_stack.StackConfig().head_saturation_floor \
        == color_stack.HEAD_SATURATION_FLOOR
    assert color_stack.StackConfig(
        head_saturation_floor=0.19).head_saturation_floor == 0.19
    # A THRESHOLD, not a measurement: above 1.0 it refuses every
    # population (the exact-null control below), below 0.0 it is nonsense.
    assert color_stack.StackConfig(
        head_saturation_floor=2.0).head_saturation_floor == 2.0
    for bad in (-0.1, float("nan")):
        with pytest.raises(ValueError, match="nonnegative fraction"):
            color_stack.StackConfig(head_saturation_floor=bad)

    fixture = build_head_fixture(*PATHOLOGICAL)
    region = collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec,
        stack_config=color_stack.StackConfig(
            head_saturation_floor=0.05)).regions[0]
    assert region.cmy7_head_saturation_floor == 0.05
    assert region.cmy7_head_adopted
    from holo.receive import _production_diagnostics

    details = {row.name: row.value for row
               in _production_diagnostics.color_region_details(region)}
    assert details["color.cmy7_head.saturation_floor"] == 0.05


def test_floor_refusal_is_reachable_and_names_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A head the furniture gate ACCEPTS is still refused below the floor.

    The synthetic pathological channel saturates ~100% of its emitted
    cells, which is why it is a positive control at all — so reachability
    is exercised by raising the floor above the population rather than by
    inventing an unsaturated render the forward model does not produce.
    """
    fixture = build_head_fixture(*PATHOLOGICAL)
    adopted = collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec)
    live = adopted.regions[0]
    assert live.cmy7_head_adopted and live.cmy7_head_reason == "adopted"
    measured = live.cmy7_baseline_saturation_fraction
    assert 0.0 <= measured <= 1.0
    assert measured >= color_stack.HEAD_SATURATION_FLOOR

    refused = collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec,
        stack_config=color_stack.StackConfig(
            head_saturation_floor=measured + 1e-6))
    region = refused.regions[0]
    assert region.cmy7_head_reason == color_stack.HEAD_SATURATION_REASON
    assert not region.cmy7_head_adopted
    # Nothing was applied, so the reported temperature is the truth: 1.0.
    assert region.cmy7_head_temperature == 1.0
    # ...and the number the floor judged is reported, not hidden.
    assert region.cmy7_baseline_saturation_fraction == measured


def test_below_floor_evidence_is_byte_identical_to_the_null_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R2 extended: a floor refusal is a NULL, not a weaker head."""
    fixture = build_head_fixture(*PATHOLOGICAL)
    # The null arm is head-refused rather than force-null (see
    # ``_refuse_head``): PK4's A3 sits below the head and would otherwise
    # be a second difference between these two runs.
    with monkeypatch.context() as without_head:
        _refuse_head(without_head)
        forced = collect_color_evidence(
            fixture.raster, fixture.source, fixture.address, fixture.spec)
    refused = collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec,
        stack_config=color_stack.StackConfig(head_saturation_floor=2.0))

    assert (refused.regions[0].cmy7_head_reason
            == color_stack.HEAD_SATURATION_REASON)
    assert forced.regions[0].cmy7_head_reason == "validation_gate_failed"
    for left, right in zip(forced.windows, refused.windows, strict=True):
        assert np.array_equal(
            np.asarray(left.evidence_values).view(np.uint8),
            np.asarray(right.evidence_values).view(np.uint8))
    # The floor measured the same population the force-null arm EMITTED:
    # below the floor, "before" and "after" are the same number.
    assert (refused.regions[0].cmy7_baseline_saturation_fraction
            == forced.regions[0].cmy7_saturation_fraction
            == refused.regions[0].cmy7_saturation_fraction)


def test_above_floor_behaviour_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the population above the floor, PK3.1 changes nothing."""
    fixture = build_head_fixture(*PATHOLOGICAL)
    live = collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec)
    floorless = collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec,
        stack_config=color_stack.StackConfig(head_saturation_floor=0.0))
    region, reference = live.regions[0], floorless.regions[0]
    assert region.cmy7_head_adopted and reference.cmy7_head_adopted
    assert region.cmy7_head_temperature == reference.cmy7_head_temperature
    assert region.cmy7_saturation_fraction == (
        reference.cmy7_saturation_fraction)
    for left, right in zip(live.windows, floorless.windows, strict=True):
        assert np.array_equal(
            np.asarray(left.evidence_values).view(np.uint8),
            np.asarray(right.evidence_values).view(np.uint8))


def test_the_floor_measures_the_emitted_population_only() -> None:
    """The floor's population is the region's own emission, exactly."""
    fixture = build_head_fixture(*PATHOLOGICAL)
    captured: list = []
    original = color_stack.fit_region_stack

    def recording(spec, selection, rows, arms, residuals, **kwargs):
        result = original(
            spec, selection, rows, arms, residuals, **kwargs)
        captured.append((result, kwargs["emission_masks"]))
        return result

    color_payload.fit_region_stack = recording
    try:
        evidence = collect_color_evidence(
            fixture.raster, fixture.source, fixture.address, fixture.spec)
    finally:
        color_payload.fit_region_stack = original

    result, masks = captured[0]
    assert masks and all(mask.dtype == np.bool_ for mask in masks)
    emitted = sum(int(np.count_nonzero(mask)) for mask in masks)
    assert emitted == sum(
        window.evidence_values.shape[0] for window in evidence.windows)
    # Re-derive the gated number from the region's OWN baseline fit,
    # head-free, through the public helper.
    from dataclasses import replace

    headless = replace(
        result.selected_fit, cmy7_head=None, head_reason="")
    assert color_stack.deployment_saturation(
        headless, result.selected_features, masks) == (
            result.head_saturation_fraction)


def test_the_ladder_requires_the_emission_masks() -> None:
    """A caller cannot silently disable the floor by omitting them."""
    fixture = build_fixture("cmy7-clean")
    captured: list = []
    original = color_stack.fit_region_stack

    def recording(spec, selection, rows, arms, residuals, **kwargs):
        captured.append((spec, selection, rows, arms, residuals))
        return original(spec, selection, rows, arms, residuals, **kwargs)

    color_payload.fit_region_stack = recording
    try:
        collect_color_evidence(
            fixture.raster, fixture.source, fixture.address, fixture.spec)
    finally:
        color_payload.fit_region_stack = original
    with pytest.raises(TypeError):
        original(*captured[0])  # type: ignore[call-arg]


def test_cmy8_regions_gain_no_head_and_no_new_diagnostics() -> None:
    """PK3 is a strict no-op on cmy8 (the replay scope check, in-suite)."""
    for key in ("cmy8-clean", "cmy8-residual"):
        fixture = build_fixture(key)
        evidence = collect_color_evidence(
            fixture.raster, fixture.source, fixture.address, fixture.spec)
        region = evidence.regions[0]
        assert region.cmy7_head_reason == ""
        assert not region.cmy7_head_adopted
        assert region.cmy7_head_temperature == 1.0
        assert region.cmy7_saturation_fraction == 0.0
        assert (region.cmy7_baseline_saturation_fraction
                == color_stack.HEAD_SATURATION_UNMEASURED)


def test_region_details_emit_head_keys_only_for_cmy7() -> None:
    from holo.receive._production_diagnostics import color_region_details

    head_keys = {
        "color.cmy7_head.adopted", "color.cmy7_head.reason",
        "color.cmy7_head.temperature",
        "color.cmy7_head.saturation_fraction",
    }
    for key, expected in (("cmy7-clean", True), ("cmy8-clean", False)):
        fixture = build_fixture(key)
        evidence = collect_color_evidence(
            fixture.raster, fixture.source, fixture.address, fixture.spec)
        names = {
            row.name
            for row in color_region_details(evidence.regions[0])}
        assert (head_keys <= names) is expected


def test_the_heldout_population_is_carried_for_cmy7_only() -> None:
    """The chosen seam: `_fit_detector` publishes what the head needs."""
    for key, expect in (("cmy7-clean", True), ("cmy8-clean", False)):
        fixture = build_fixture(key)
        _selection, _base, result = _cmy7_fit(fixture)
        population = result.selected_fit.heldout_population
        assert (population is not None) is expect
        if not expect:
            continue
        assert population.relative_scores.shape == (
            population.states.size, HEAD_N_OFFSETS)
        assert population.site_keys.shape == (population.states.size, 3)
        # The two populations really are the two sides of the QDA split.
        assert (population.site_keys.shape[0]
                + population.search_site_keys.shape[0]
                == result.selected_fit.n_train
                + result.selected_fit.n_heldout)

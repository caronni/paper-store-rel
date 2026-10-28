"""Phase-7 detect.py unit pins (PAYLOAD-REWORK-PLAN 7.1a, lens-coverage:05).

detect.py is the receiver's self-declared numerical evidence boundary
(calibrate-or-refuse floors, the one context clip kernel, held-out strict
improvement).  Until this file every §6.2 rule rode integration only; the
measured-channel stress gate is slow-only.  These are unit-scale synthetic
populations — each floor, clamp, and refusal branch is exercised directly.
"""
from __future__ import annotations

import numpy as np
import pytest

from holo.receive import detect


# ---------------------------------------------------------------------------
# builders


def _marginal(window_id: str, n0: int, n1: int, *, id_base: int = 0,
              spread: float = 1.0) -> detect.CalibrationObservations:
    """A separable two-class score population with unique site ids."""
    scores = np.concatenate((
        np.linspace(-3.0, -1.0, n0) * spread,
        np.linspace(1.0, 3.0, n1) * spread,
    ))
    labels = np.concatenate((np.zeros(n0, np.int8), np.ones(n1, np.int8)))
    ids = np.arange(id_base, id_base + n0 + n1, dtype=np.int64)
    return detect.CalibrationObservations(window_id, scores, labels, ids)


def _context_population(
    region_id: str,
    n_per_bin: int,
    *,
    id_base: int = 0,
    bias_per_bin: float = 0.5,
    biased: bool = True,
) -> detect.ContextObservations:
    """Balanced labels per bin; the marginal LLR carries a per-bin bias.

    The physical story is E023b's: ink-dense neighbourhoods read darker, so
    the marginal evidence is biased increasingly positive with neighbour
    ink count; the correct additive correction is non-increasing in the
    bin index.  ``biased=False`` builds the same population with the truth
    already unbiased (a context arm can only hurt or tie there).
    """
    counts, llrs, labels, ids = [], [], [], []
    next_id = id_base
    for bin_index in range(detect.N_CONTEXT_BINS):
        for row in range(n_per_bin):
            label = row % 2 == 0
            true_llr = 2.0 if label else -2.0
            bias = bias_per_bin * (bin_index - 4) if biased else 0.0
            counts.append(bin_index)
            llrs.append(true_llr + bias)
            labels.append(label)
            ids.append(next_id)
            next_id += 1
    return detect.ContextObservations(
        region_id,
        np.asarray(llrs, np.float64),
        np.asarray(counts, np.int64),
        np.asarray(labels, np.int8),
        np.asarray(ids, np.int64),
    )


# ---------------------------------------------------------------------------
# marginal calibrate-or-refuse floors (CAL_MIN_*)


def test_marginal_floor_constants_are_the_frozen_e023_bars() -> None:
    assert detect.CAL_MIN_PER_CLASS == 10
    assert detect.CAL_MIN_HELDOUT == 10


def test_search_class_floor_refuses_just_below_and_accepts_at_bar() -> None:
    heldout = _marginal("w", 8, 8, id_base=10_000)
    starved = detect.fit_calibration(
        _marginal("w", detect.CAL_MIN_PER_CLASS - 1,
                  detect.CAL_MIN_PER_CLASS), heldout)
    assert not starved.accepted
    assert starved.calibration is None
    assert starved.reason == "search_class_starved"
    assert starved.heldout_logloss is None

    # The other class starved refuses identically.
    starved_ones = detect.fit_calibration(
        _marginal("w", detect.CAL_MIN_PER_CLASS,
                  detect.CAL_MIN_PER_CLASS - 1), heldout)
    assert starved_ones.reason == "search_class_starved"

    accepted = detect.fit_calibration(
        _marginal("w", detect.CAL_MIN_PER_CLASS,
                  detect.CAL_MIN_PER_CLASS), heldout)
    assert accepted.accepted and accepted.reason == "accepted"
    assert accepted.calibration is not None
    assert accepted.heldout_logloss is not None


def test_heldout_floor_refuses_just_below_and_accepts_at_bar() -> None:
    search = _marginal("w", 12, 12)
    starved = detect.fit_calibration(
        search, _marginal("w", 5, detect.CAL_MIN_HELDOUT - 6,
                          id_base=10_000))
    assert not starved.accepted
    assert starved.reason == "heldout_starved"

    # HELDOUT is a total-count bar (ownership/honesty, not quality): a
    # one-sided held-out population at the bar still accepts.
    one_sided = detect.fit_calibration(
        search, _marginal("w", detect.CAL_MIN_HELDOUT, 0, id_base=10_000))
    assert one_sided.accepted


def test_search_class_floor_outranks_heldout_floor() -> None:
    fit = detect.fit_calibration(
        _marginal("w", 3, 30), _marginal("w", 2, 2, id_base=10_000))
    assert fit.reason == "search_class_starved"


# ---------------------------------------------------------------------------
# deterministic partition properties


def test_partition_leakage_and_identity_mismatches_refuse() -> None:
    search = _marginal("w", 12, 12)
    with pytest.raises(ValueError, match="site ids overlap"):
        detect.fit_calibration(search, _marginal("w", 8, 8, id_base=0))
    with pytest.raises(ValueError, match="different windows"):
        detect.fit_calibration(
            search, _marginal("other", 8, 8, id_base=10_000))


def test_marginal_duplicate_site_ids_refuse() -> None:
    with pytest.raises(ValueError, match="duplicate physical labels"):
        detect.CalibrationObservations(
            "w", np.asarray([0.0, 1.0]), np.asarray([0, 1]),
            np.asarray([7, 7]))


def test_fit_is_deterministic_and_monotone() -> None:
    heldout = _marginal("w", 10, 10, id_base=10_000)
    first = detect.fit_calibration(_marginal("w", 15, 15), heldout)
    second = detect.fit_calibration(_marginal("w", 15, 15), heldout)
    assert first.calibration is not None and second.calibration is not None
    np.testing.assert_array_equal(
        first.calibration.knots, second.calibration.knots)
    np.testing.assert_array_equal(
        first.calibration.probabilities, second.calibration.probabilities)
    assert first.heldout_logloss == second.heldout_logloss
    assert np.all(np.diff(first.calibration.probabilities) >= 0.0)


# ---------------------------------------------------------------------------
# the bounded-LLR invariant at the emission boundary (the 018.7 lesson)


def test_calibration_llr_is_bounded_by_the_pava_support() -> None:
    """|LLR| <= log(n_search + 1) exactly, even at wild scores.

    018.7 (LLR honesty): unbounded confidence from a finite calibration
    population is a lie the decoder will believe.  pava-v1 enforces the
    bound through pmin = 1/(n+2); ``clamp_for`` is its closed form.
    """
    fit = detect.fit_calibration(
        _marginal("w", 40, 40), _marginal("w", 10, 10, id_base=10_000))
    assert fit.calibration is not None
    bound = detect.clamp_for(fit.n_search)
    assert bound == pytest.approx(float(np.log1p(fit.n_search)))
    wild = np.asarray([-1e9, -5.0, 0.0, 5.0, 1e9])
    llr = fit.calibration.llr(wild)
    assert np.all(np.abs(llr) <= bound + 1e-12)
    # The bound is attained at the extremes (pmin really is the floor).
    assert np.abs(llr[0]) == pytest.approx(bound)
    assert np.abs(llr[-1]) == pytest.approx(bound)


def test_calibration_probability_outside_pava_support_refuses() -> None:
    with pytest.raises(ValueError, match="PAVA support"):
        detect.Calibration(
            "w", np.asarray([0.0, 1.0]), np.asarray([0.001, 0.999]),
            n_search=10)


def test_clamp_for_refuses_non_positive_and_non_integer() -> None:
    for bad in (0, -1, 1.5, True):
        with pytest.raises(ValueError):
            detect.clamp_for(bad)


def test_non_finite_scores_refuse_at_both_boundaries() -> None:
    with pytest.raises(ValueError, match="finite"):
        detect.CalibrationObservations(
            "w", np.asarray([np.nan, 1.0]), np.asarray([0, 1]),
            np.asarray([0, 1]))
    fit = detect.fit_calibration(
        _marginal("w", 12, 12), _marginal("w", 8, 8, id_base=10_000))
    assert fit.calibration is not None
    with pytest.raises(ValueError, match="finite"):
        fit.calibration.llr(np.asarray([np.inf]))


# ---------------------------------------------------------------------------
# context floors (ctx-pava-v1 refusal ladder)


def _starved_context_fit(
    n_search_per_bin: int,
    n_validation_per_bin: int,
    *,
    search_one_sided: bool = False,
    validation_one_sided: bool = False,
) -> detect.ContextFit:
    def build(region, n_per_bin, one_sided, id_base):
        pop = _context_population(region, n_per_bin, id_base=id_base)
        if not one_sided:
            return pop
        # Collapse to (almost) one class: relabel all but one row per class
        # boundary by rebuilding with labels mostly zero.
        counts = pop.neighbour_count.copy()
        llrs = pop.baseline_llr.copy()
        labels = np.zeros(pop.labels.size, np.int8)
        labels[:2] = 1  # below the per-class bar, above zero
        return detect.ContextObservations(
            region, llrs, counts, labels, pop.site_ids)

    search = build("r", n_search_per_bin, search_one_sided, 0)
    validation = build(
        "r", n_validation_per_bin, validation_one_sided, 100_000)
    return detect.fit_context(search, validation)


def test_context_floor_ladder_each_reason() -> None:
    assert detect.CTX_MIN_SEARCH == 80
    assert detect.CTX_MIN_SEARCH_PER_CLASS == 20
    assert detect.CTX_MIN_VALIDATION == 40
    assert detect.CTX_MIN_VALIDATION_PER_CLASS == 10

    # 8/bin * 9 bins = 72 < 80 total-search floor.
    fit = _starved_context_fit(8, 6)
    assert not fit.eligible and not fit.adopted
    assert fit.reason == "insufficient_search_support"
    np.testing.assert_array_equal(
        fit.offsets, np.zeros(detect.N_CONTEXT_BINS))
    assert fit.baseline_validation_logloss is None

    # Enough total search, one class starved.
    fit = _starved_context_fit(12, 6, search_one_sided=True)
    assert fit.reason == "search_class_starved"

    # 4/bin * 9 = 36 < 40 total-validation floor.
    fit = _starved_context_fit(12, 4)
    assert fit.reason == "insufficient_validation_support"

    # Enough total validation, one class starved.
    fit = _starved_context_fit(12, 6, validation_one_sided=True)
    assert fit.reason == "validation_class_starved"

    # At the bars: eligible.
    fit = _starved_context_fit(12, 6)
    assert fit.eligible


def test_context_partition_leakage_refuses() -> None:
    search = _context_population("r", 12)
    with pytest.raises(ValueError, match="site ids overlap"):
        detect.fit_context(search, _context_population("r", 6))
    with pytest.raises(ValueError, match="different regions"):
        detect.fit_context(
            search, _context_population("other", 6, id_base=100_000))


# ---------------------------------------------------------------------------
# held-out strict-improvement adoption


def test_context_adopts_only_on_strict_heldout_improvement() -> None:
    search = _context_population("r", 12, bias_per_bin=0.5)
    validation = _context_population(
        "r", 6, id_base=100_000, bias_per_bin=0.5)
    fit = detect.fit_context(search, validation)
    assert fit.eligible and fit.adopted and fit.reason == "adopted"
    assert fit.candidate_validation_logloss < fit.baseline_validation_logloss
    # The correction is genuinely ordered and bounded.
    assert np.all(np.diff(fit.offsets) <= 1e-10)
    assert np.max(np.abs(fit.offsets)) <= detect.CTX_OFFSET_LIMIT + 1e-10


def test_context_leaves_unbiased_evidence_exactly_untouched() -> None:
    """A symmetric unbiased region solves offsets == 0 exactly, the
    candidate ties the baseline, and the strict gate refuses adoption —
    the marginal evidence stays exactly untouched."""
    search = _context_population("r", 12, biased=False)
    validation = _context_population("r", 6, id_base=100_000, biased=False)
    fit = detect.fit_context(search, validation)
    assert fit.eligible and not fit.adopted
    assert fit.reason == "validation_gate_failed"
    np.testing.assert_array_equal(
        fit.offsets, np.zeros(detect.N_CONTEXT_BINS))
    assert (fit.candidate_validation_logloss
            == fit.baseline_validation_logloss)


def test_context_fit_record_refuses_inconsistent_adoption() -> None:
    good = detect.fit_context(
        _context_population("r", 12),
        _context_population("r", 6, id_base=100_000))
    assert good.adopted
    import dataclasses
    with pytest.raises(ValueError, match="improve held-out loss"):
        dataclasses.replace(
            good,
            candidate_validation_logloss=good.baseline_validation_logloss)
    with pytest.raises(ValueError, match="cannot be adopted"):
        dataclasses.replace(good, eligible=False)


# ---------------------------------------------------------------------------
# duplicate-weight handling (total weight one per physical site)


def test_duplicate_observations_of_one_site_have_total_weight_one() -> None:
    base = _context_population("r", 12)
    # Triplicate every observation of the first 30 sites.
    dup_rows = np.flatnonzero(base.site_ids < 30)
    counts = np.concatenate(
        (base.neighbour_count,) + (base.neighbour_count[dup_rows],) * 2)
    llrs = np.concatenate(
        (base.baseline_llr,) + (base.baseline_llr[dup_rows],) * 2)
    labels = np.concatenate(
        (base.labels,) + (base.labels[dup_rows],) * 2)
    ids = np.concatenate(
        (base.site_ids,) + (base.site_ids[dup_rows],) * 2)
    duplicated = detect.ContextObservations("r", llrs, counts, labels, ids)

    multiplicity = np.where(duplicated.site_ids < 30, 3.0, 1.0)
    np.testing.assert_allclose(duplicated.weights, 1.0 / multiplicity)

    validation = _context_population("r", 6, id_base=100_000)
    from_dup = detect.fit_context(duplicated, validation)
    from_base = detect.fit_context(base, validation)
    # Same unique class support and the same solved offsets: duplicates
    # cannot outvote a physical label.
    assert from_dup.n_search == from_base.n_search
    np.testing.assert_allclose(
        from_dup.offsets, from_base.offsets, atol=1e-9)
    assert from_dup.adopted == from_base.adopted


def test_conflicting_labels_for_one_physical_site_refuse() -> None:
    with pytest.raises(ValueError, match="conflicting labels"):
        detect.ContextObservations(
            "r",
            np.asarray([1.0, 1.0]),
            np.asarray([4, 4]),
            np.asarray([0, 1]),
            np.asarray([7, 7]))


# ---------------------------------------------------------------------------
# CTX_LLR_CLAMP application (the one shared clip kernel)


def test_apply_context_offsets_clamps_and_skips_invalid_bins() -> None:
    assert detect.CTX_LLR_CLAMP == 12.0
    llr = np.asarray([11.5, -11.5, 3.0, 20.0, -20.0], np.float64)
    bins = np.asarray([8, 0, 4, -1, -1], np.int8)
    offsets = np.linspace(4.0, -4.0, detect.N_CONTEXT_BINS)
    out = detect.apply_context_offsets(llr, bins, offsets)
    # Corrected cells clip at exactly +-CTX_LLR_CLAMP.
    np.testing.assert_allclose(
        out[:3],
        np.clip(llr[:3] + offsets[bins[:3]],
                -detect.CTX_LLR_CLAMP, detect.CTX_LLR_CLAMP))
    assert out[0] <= detect.CTX_LLR_CLAMP
    # Invalid-context cells keep their marginal value UNCHANGED, even
    # beyond the clamp: the clip belongs to the correction, not the input.
    assert out[3] == 20.0 and out[4] == -20.0
    # Fresh array; the input is never mutated.
    assert out is not llr
    assert llr[0] == 11.5


def test_apply_context_offsets_saturates_at_clamp() -> None:
    llr = np.full(9, 11.0)
    bins = np.arange(9, dtype=np.int8)
    up = np.full(9, detect.CTX_OFFSET_LIMIT)
    out = detect.apply_context_offsets(llr, bins, up)
    np.testing.assert_array_equal(out, np.full(9, detect.CTX_LLR_CLAMP))
    down = -up
    out = detect.apply_context_offsets(-llr, bins, down)
    np.testing.assert_array_equal(out, np.full(9, -detect.CTX_LLR_CLAMP))


# ---------------------------------------------------------------------------
# context bin arithmetic


def test_context_bins_and_neighbour_counts_agree_on_a_dense_patch() -> None:
    yy, xx = np.indices((5, 5))
    cells = np.stack((yy.ravel(), xx.ravel()), axis=1).astype(np.int64)
    ink = (cells.sum(axis=1) % 2).astype(np.int8)  # checkerboard
    counts, complete = detect.context_neighbour_counts(cells, ink)
    # Interior checkerboard cells see exactly 4 inked neighbours.
    interior = complete.nonzero()[0]
    assert interior.size == 9
    assert set(counts[interior].tolist()) == {4}
    bins = detect.context_bins(counts, valid=complete)
    assert np.all(bins[interior] == 4)
    assert np.all(bins[~complete] == -1)


def test_context_bins_refuse_out_of_range_counts() -> None:
    with pytest.raises(ValueError, match="0..8"):
        detect.context_bins(np.asarray([9]))
    with pytest.raises(ValueError, match="0..8"):
        detect.context_bins(np.asarray([-2]))
    with pytest.raises(ValueError, match="integers"):
        detect.context_bins(np.asarray([1.5]))

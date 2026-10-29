"""W1d: combination across lanes — DESIGN §5.

Synthetic only.  Every rule here is a function of per-lane LLR vectors
and per-lane label views, both of which the tests build directly; the
sheet-I evidence that feeds them is exercised in
`test_analyzer_arms.py`'s parity leg.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

from holo.receiver.lib import ldpc

from analyzer import combine as comb
from analyzer.types import Evidence

KEY = (0, 5, 6, "Y")


def _evidence(capture: str, level: int, llr: np.ndarray, *,
              observed: np.ndarray | None = None,
              label_rows=None, label_llr=None, label_values=None,
              discriminating: bool = True,
              select_logloss: float = 0.5) -> Evidence:
    llr = np.asarray(llr, np.float64)
    seen = np.ones(llr.size, bool) if observed is None else observed
    blind = {"heldout_logloss_select": select_logloss}
    if label_rows is not None:
        n = len(label_rows)
        blind.update({
            "label_rows": np.asarray(label_rows, np.int64),
            "label_llr": np.asarray(label_llr, np.float64),
            "label_values": np.asarray(label_values, np.uint8),
            "label_discriminating": np.full(n, discriminating)})
    return Evidence(key=KEY, lane=(capture, level), arm="subtract+committed",
                    llr_sequential=llr, observed=seen, blind=blind)


def _labelled_lanes(n_labels: int, seed: int, strengths, *,
                    discriminating: bool = True, n_cells: int = 64):
    rng = np.random.default_rng(seed)
    values = rng.integers(0, 2, n_labels, dtype=np.uint8)
    signal = 2.0 * values.astype(np.float64) - 1.0
    rows = np.arange(n_labels, dtype=np.int64)
    lanes = []
    for index, strength in enumerate(strengths):
        lanes.append(_evidence(
            f"capture{index:02d}" * 2, 3,
            rng.normal(0.0, 1.0, n_cells),
            label_rows=rows,
            label_llr=strength * signal + rng.normal(0.0, 1.0, n_labels),
            label_values=values, discriminating=discriminating,
            select_logloss=1.0 / (1.0 + strength)))
    return lanes, rows, values


# ------------------------------------------------------------ de-duping

def test_one_capture_contributes_one_vector_finest_level_wins():
    """DESIGN §0's physical-evidence invariant."""
    coarse = _evidence("aaaaaaaaaaaa", 1, np.full(8, 1.0))
    fine = _evidence("aaaaaaaaaaaa", 3, np.full(8, 2.0))
    other = _evidence("bbbbbbbbbbbb", 2, np.full(8, 4.0))
    result = comb.combine((coarse, fine, other), "sum")
    assert result.lanes == (("aaaaaaaaaaaa", 3), ("bbbbbbbbbbbb", 2))
    assert np.allclose(result.llr_sequential, 6.0)


def test_de_dup_prefers_the_larger_ppc_when_one_is_offered():
    coarse = _evidence("aaaaaaaaaaaa", 5, np.full(4, 1.0))
    fine = _evidence("aaaaaaaaaaaa", 2, np.full(4, 9.0))
    ppc = {("aaaaaaaaaaaa", 5): Fraction(2), ("aaaaaaaaaaaa", 2): Fraction(8)}
    result = comb.combine((coarse, fine), "sum", lane_ppc=ppc)
    assert result.lanes == (("aaaaaaaaaaaa", 2),)


def test_combine_refuses_two_keys_in_one_call():
    left = _evidence("aaaaaaaaaaaa", 1, np.full(4, 1.0))
    right = Evidence(key=(0, 5, 7, "Y"), lane=("bbbbbbbbbbbb", 1),
                     arm="subtract+committed",
                     llr_sequential=np.full(4, 1.0),
                     observed=np.ones(4, bool), blind={})
    with pytest.raises(comb.CombineError):
        comb.combine((left, right), "sum")


# ---------------------------------------------------------------- rules

def test_sum_only_prices_observed_cells():
    seen = np.array([True, True, False, False])
    left = _evidence("aaaaaaaaaaaa", 1, np.array([1.0, 2.0, 3.0, 4.0]),
                     observed=seen)
    right = _evidence("bbbbbbbbbbbb", 1, np.array([1.0, 0.0, 0.0, 0.0]),
                      observed=np.array([True, False, False, False]))
    result = comb.combine((left, right), "sum")
    assert np.allclose(result.llr_sequential, [2.0, 2.0, 0.0, 0.0])
    assert np.array_equal(result.observed, [True, True, False, False])


def test_normalized_is_the_mean_and_cannot_clip():
    lanes = [_evidence(f"capture{index}" * 2, 1, np.full(4, 30.0))
             for index in range(3)]
    summed = comb.combine(lanes, "sum")
    mean = comb.combine(lanes, "normalized")
    assert np.allclose(mean.llr_sequential, 30.0)
    assert summed.clipped_fraction == 1.0
    assert mean.clipped_fraction == 1.0 * (30.0 >= ldpc.LLR_CLIP)


def test_best_picks_the_lane_with_the_lowest_select_loss():
    lanes, _rows, _values = _labelled_lanes(200, 12, (0.2, 4.0, 0.5))
    result = comb.combine(lanes, "best")
    assert result.coefficients == (0.0, 1.0, 0.0)
    assert result.lanes[int(np.argmax(result.coefficients))][0].startswith(
        "capture01")


def test_platt_refuses_to_sum_below_the_label_floor():
    """DESIGN §5: `platt` is fitted or it is not used."""
    lanes, _rows, _values = _labelled_lanes(20, 3, (1.0, 1.0))
    result = comb.combine(lanes, "platt")
    assert result.rule == "platt"
    assert np.allclose(result.coefficients, 1.0), "fell back to sum"
    fresh = comb.combine(lanes, "sum")
    assert np.allclose(result.llr_sequential, fresh.llr_sequential)


def test_platt_refuses_when_no_label_discriminates():
    lanes, _rows, _values = _labelled_lanes(
        400, 4, (1.0, 1.0), discriminating=False)
    result = comb.combine(lanes, "platt")
    assert np.allclose(result.coefficients, 1.0)


def test_platt_down_weights_a_useless_lane_above_the_floor():
    lanes, _rows, _values = _labelled_lanes(600, 5, (4.0, 0.0))
    result = comb.combine(lanes, "platt")
    weights = np.asarray(result.coefficients)
    assert np.all(weights >= 0.0), "beta must be non-negative"
    assert weights[0] > weights[1] * 3.0, weights


def test_corr_shrinks_a_sum_of_correlated_lanes():
    """The multi-scan law: print-frozen errors are correlated."""
    rng = np.random.default_rng(7)
    n_labels, n_cells = 400, 32
    values = rng.integers(0, 2, n_labels, dtype=np.uint8)
    signal = 2.0 * values.astype(np.float64) - 1.0
    shared = rng.normal(0.0, 3.0, n_labels)
    rows = np.arange(n_labels, dtype=np.int64)
    correlated = [
        _evidence(f"capture{index}" * 2, 1, rng.normal(0, 1, n_cells),
                  label_rows=rows, label_llr=signal + shared,
                  label_values=values) for index in range(3)]
    independent = [
        _evidence(f"capture{index}" * 2, 1, rng.normal(0, 1, n_cells),
                  label_rows=rows,
                  label_llr=signal + rng.normal(0.0, 3.0, n_labels),
                  label_values=values) for index in range(3)]
    tight = comb.combine(correlated, "corr")
    loose = comb.combine(independent, "corr")
    assert tight.coefficients[0] < loose.coefficients[0]
    assert tight.coefficients[0] < 1.0
    assert loose.coefficients[0] == pytest.approx(1.0, abs=0.15)


def test_every_rule_reports_its_coefficients_and_clipped_fraction():
    lanes, _rows, _values = _labelled_lanes(400, 9, (2.0, 2.0, 0.1))
    for rule in comb.RULES:
        result = comb.combine(lanes, rule)
        assert len(result.coefficients) == len(result.lanes)
        assert 0.0 <= result.clipped_fraction <= 1.0
        summary = comb.combine_detail(result)
        assert summary["rule"] == rule

# --------------------------------------------- lane agreement (L7a's input)

def _three_lanes():
    """Six cells with planted sign structure; `sum` is the combination.

    cell 0  all three agree (+)              agreement 1
    cell 1  one lane dissents, sum stays +   agreement 2/3
    cell 2  the dissenter is the loud one    agreement 1/3
    cell 3  one lane priced nothing, the other two cancel exactly
    cell 4  only one lane priced it at all   not eligible (n_voting 1)
    cell 5  all three agree (-)              agreement 1
    """
    a = np.array([2.0, 3.0, 1.0, 0.0, 5.0, -2.0])
    b = np.array([2.0, -1.0, -3.0, 2.0, 0.0, -2.0])
    c = np.array([2.0, 1.0, 1.0, -2.0, 0.0, -2.0])
    return (_evidence("aaaaaaaaaaaa", 3, a), _evidence("bbbbbbbbbbbb", 3, b),
            _evidence("cccccccccccc", 3, c))


def test_lane_agreement_finds_the_planted_disagreements():
    result = comb.combine(_three_lanes(), "sum")
    assert np.allclose(result.llr_sequential, [6.0, 3.0, -1.0, 0.0, 5.0, -6.0])
    assert np.allclose(result.agreement,
                       [1.0, 2.0 / 3.0, 1.0 / 3.0, 0.0, 1.0, 1.0])
    assert result.disagree.tolist() == [1, 2, 3]
    assert not result.agreement.flags.writeable


def test_lane_agreement_threshold_selects_the_badly_split_cells():
    result = comb.combine(_three_lanes(), "sum", agreement_threshold=0.5)
    assert result.disagree.tolist() == [2, 3]


def test_an_unobserved_or_unpriced_lane_does_not_vote():
    a, b, c = _three_lanes()
    hidden = np.ones(6, bool)
    hidden[1] = False                       # lane b saw nothing at cell 1
    b = Evidence(key=b.key, lane=b.lane, arm=b.arm,
                 llr_sequential=b.llr_sequential, observed=hidden,
                 blind=dict(b.blind))
    result = comb.combine((a, b, c), "sum")
    assert result.agreement[1] == 1.0       # a and c agree; b abstains
    assert result.disagree.tolist() == [2, 3]


def test_a_single_lane_produces_no_disagreement_set():
    """L7a refuses on one-lane rules exactly as it did before W4."""
    only = _evidence("aaaaaaaaaaaa", 3, np.array([1.0, -1.0, 2.0]))
    result = comb.combine((only,), "sum")
    assert result.disagree is None and result.agreement is None
    assert comb.combine_detail(result)["n_disagreeing"] is None


def test_best_reduces_the_disagreement_set_to_its_own_lane():
    """`best` zeroes the other lanes' coefficients, but the VOTES are
    physical: the set is about what the captures read, not about weights."""
    result = comb.combine(_three_lanes(), "best")
    assert int(np.count_nonzero(result.coefficients)) == 1
    assert result.disagree.size >= 1


def test_combine_detail_reports_counts_not_the_agreement_vector():
    detail = comb.combine_detail(comb.combine(_three_lanes(), "sum"))
    assert detail["n_disagreeing"] == 3
    assert 0.0 < detail["mean_agreement"] <= 1.0
    assert "agreement" not in detail


# ------------------------- independent certificate agreement (2026-09-04)
#
# Leg 4 of the correctness ruling.  Distinct from the per-cell agreement
# above in every way that matters: it compares FINISHED certificates, its
# unit is the whole key rather than a cell, and its independence test is
# whether two certificates rest on disjoint PHYSICAL CAPTURES — not on
# distinct rules, which read the same paper twice.


def _claim(label: str, captures, bits, *, rung: str = "L0",
           verdict: str = "certified") -> comb.CertificateClaim:
    return comb.CertificateClaim(
        label=label, rung=rung, verdict=verdict,
        captures=frozenset(captures),
        user_bits=np.asarray(bits, np.uint8))


BITS_A = np.array([1, 0, 1, 1, 0, 0, 1, 0], np.uint8)
BITS_B = np.array([1, 0, 1, 1, 0, 0, 1, 1], np.uint8)     # one bit apart


def test_contributing_captures_drops_the_lanes_a_rule_zeroed():
    """Under `best` a certificate rests on ONE capture, not on all of them."""
    result = comb.combine(_three_lanes(), "best")
    detail = comb.combine_detail(result)
    captures = comb.contributing_captures(detail)
    assert len(captures) == 1
    assert captures <= {"aaaaaaaaaaaa", "bbbbbbbbbbbb", "cccccccccccc"}
    summed = comb.combine_detail(comb.combine(_three_lanes(), "sum"))
    assert comb.contributing_captures(summed) == {
        "aaaaaaaaaaaa", "bbbbbbbbbbbb", "cccccccccccc"}


def test_no_claims_is_zero_agreement_and_no_contradiction():
    report = comb.independent_agreement([])
    assert report["n_claims"] == 0
    assert report["independent_agreement"] == 0
    assert report["contradiction"] is False


def test_one_certificate_corroborates_nothing():
    report = comb.independent_agreement([_claim("sum", {"a", "b"}, BITS_A)])
    assert report["independent_agreement"] == 1
    assert report["contradiction"] is False
    assert report["n_distinct_bits"] == 1


def test_two_rules_over_the_same_lanes_are_ONE_observation():
    """The physical-evidence invariant (DESIGN §0), enforced here.

    `sum` and `corr` differ only by a positive scale factor, so a key
    they both certify was read once, not twice.  Counting that as
    corroboration would be the multi-scan law's exact mistake.
    """
    report = comb.independent_agreement([
        _claim("sum", {"a", "b", "c"}, BITS_A),
        _claim("corr", {"a", "b", "c"}, BITS_A)])
    assert report["n_claims"] == 2
    assert report["independent_agreement"] == 1


def test_disjoint_captures_agreeing_bit_for_bit_corroborate():
    report = comb.independent_agreement([
        _claim("best", {"a"}, BITS_A),
        _claim("sum|reroll:field", {"b"}, BITS_A)])
    assert report["independent_agreement"] == 2
    assert report["contradiction"] is False
    assert [item["captures"] for item in report["independent_claims"]] == [
        ["a"], ["b"]]


def test_a_third_claim_that_overlaps_does_not_add_to_the_count():
    report = comb.independent_agreement([
        _claim("best", {"a"}, BITS_A),
        _claim("best2", {"b"}, BITS_A),
        _claim("sum", {"a", "b", "c"}, BITS_A)])
    assert report["n_claims"] == 3
    assert report["independent_agreement"] == 2      # the `sum` overlaps both


def test_a_claim_resting_on_no_capture_is_not_evidence():
    report = comb.independent_agreement([
        _claim("best", {"a"}, BITS_A), _claim("ghost", set(), BITS_A)])
    assert report["independent_agreement"] == 1


def test_two_certificates_with_different_bits_are_a_contradiction():
    """Both passed syndrome AND CRC, so one is a false accept.

    Nothing blind can say which, so the report refuses rather than
    picking — and it refuses even when the two share a capture, because
    that is the same impossibility with less excuse.
    """
    report = comb.independent_agreement([
        _claim("best", {"a"}, BITS_A), _claim("sum", {"a", "b"}, BITS_B)])
    assert report["contradiction"] is True
    assert report["n_distinct_bits"] == 2
    assert report["independent_agreement"] == 0
    assert report["contradicting"][1]["n_bits_differing_from_first"] == 1
    assert "different bits" in report["refusal"]


def test_a_contradiction_between_disjoint_captures_refuses_too():
    report = comb.independent_agreement([
        _claim("best", {"a"}, BITS_A), _claim("best2", {"b"}, BITS_B)])
    assert report["contradiction"] is True
    assert report["independent_agreement"] == 0


def test_ragged_bit_vectors_are_a_contradiction_and_say_so():
    report = comb.independent_agreement([
        _claim("best", {"a"}, BITS_A),
        _claim("best2", {"b"}, np.zeros(4, np.uint8))])
    assert report["contradiction"] is True
    assert report["contradicting"][1]["n_bits_differing_from_first"] == -1

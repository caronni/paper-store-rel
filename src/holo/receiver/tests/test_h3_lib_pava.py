from __future__ import annotations

import ast
import struct

import numpy as np
import pytest

from holo.receiver.lib import pava
from holo.receiver.tests import _h3_support

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_canonical_two_branch_sigmoid_is_frozen_bit_for_bit`.

CAL_MIN_PER_CLASS = 10
CAL_MIN_HELDOUT = 10
# the log-odds the calibration probability floor is derived from: the
# decoder's own LLR_CLIP, lib/ldpc.py
CAL_FLOOR_LOG_ODDS = 20.0

N_CONTEXT_BINS = 9
CTX_OFFSET_LIMIT = 4.0
CTX_LLR_CLAMP = 12.0
CTX_BIN_PRIOR = 1.0
CTX_MIN_SEARCH = 80
CTX_MIN_SEARCH_PER_CLASS = 20
CTX_MIN_VALIDATION = 40
CTX_MIN_VALIDATION_PER_CLASS = 10
CTX_ROOT_TOL = 1e-12

PAVA_RUN_RATIO_DIVISOR = 3
PAVA_INDEX_BITS = 32
PAVA_INDEX_LIMIT = 1 << 32
F32_SIGN_BIT = 0x80000000
F32_MAGNITUDE_MASK = 0x7FFFFFFF
F32_INFINITY_BITS = 0x7F800000

# recorded 2026-08-29 on machine 4's free-threaded 3.14 venv (then named
# env314t): big-endian IEEE-754 bytes of the project-canonical
# two-branch sigmoid on a fixed probe grid
SIGMOID_PROBES = (
    (-40.0, "3c539792499b1a24"),
    (-12.0, "3ed9c541dac42246"),
    (-4.0, "3f926afa1e43c2c2"),
    (-1.0, "3fd136561454ba86"),
    (-0.5, "3fd829a0565978df"),
    (-1e-09, "3fdfffffffbb47d1"),
    (0.0, "3fe0000000000000"),
    (1e-09, "3fe0000000225c18"),
    (0.5, "3fe3eb2fd4d34391"),
    (1.0, "3fe764d4f5d5a2bd"),
    (4.0, "3fef6ca82f0de1ea"),
    (12.0, "3feffff31d5f129e"),
    (40.0, "3ff0000000000000"),
    (700.0, "3ff0000000000000"),
    (-700.0, "00d14f2b0fb9307f"),
)

MONOTONE_LADDER_SAMPLES = 300
MONOTONE_LADDER_NODES = (0.0033112582781456954, 0.9966887417218543)

BANNED_CALIBRATION_SYMBOL = "expit"


def _hex(value: float) -> str:
    return struct.pack(">d", float(value)).hex()


def test_calibration_support_floors_are_the_bar_the_plugin_boundary_uses():
    assert pava.CAL_MIN_PER_CLASS == CAL_MIN_PER_CLASS
    assert pava.CAL_MIN_HELDOUT == CAL_MIN_HELDOUT


def test_context_constants_are_the_frozen_detector_floor():
    assert pava.N_CONTEXT_BINS == N_CONTEXT_BINS
    assert pava.CTX_OFFSET_LIMIT == CTX_OFFSET_LIMIT
    assert pava.CTX_LLR_CLAMP == CTX_LLR_CLAMP
    assert pava.CTX_BIN_PRIOR == CTX_BIN_PRIOR
    assert pava.CTX_MIN_SEARCH == CTX_MIN_SEARCH
    assert pava.CTX_MIN_SEARCH_PER_CLASS == CTX_MIN_SEARCH_PER_CLASS
    assert pava.CTX_MIN_VALIDATION == CTX_MIN_VALIDATION
    assert pava.CTX_MIN_VALIDATION_PER_CLASS == CTX_MIN_VALIDATION_PER_CLASS
    assert pava.CTX_ROOT_TOL == CTX_ROOT_TOL


def test_pava_stable_order_constants_match_the_float32_bit_layout():
    assert pava.PAVA_RUN_RATIO_DIVISOR == PAVA_RUN_RATIO_DIVISOR
    assert pava.PAVA_INDEX_BITS == PAVA_INDEX_BITS
    assert pava.PAVA_INDEX_LIMIT == PAVA_INDEX_LIMIT
    assert pava.F32_SIGN_BIT == F32_SIGN_BIT
    assert pava.F32_MAGNITUDE_MASK == F32_MAGNITUDE_MASK
    assert pava.F32_INFINITY_BITS == F32_INFINITY_BITS
    assert np.float32(-0.0).view(np.uint32) == F32_SIGN_BIT
    assert np.float32(np.inf).view(np.uint32) == F32_INFINITY_BITS


@pytest.mark.parametrize("probe, expected_hex", SIGMOID_PROBES)
def test_canonical_two_branch_sigmoid_is_frozen_bit_for_bit(
        probe, expected_hex):
    value = pava.sigmoid(np.asarray([probe], np.float64))[0]
    _h3_support.assert_measured(f"sigmoid({probe!r})", _hex(value),
                               expected_hex)


def test_the_naive_one_branch_sigmoid_is_not_the_same_function():
    probes = np.asarray([probe for probe, _ in SIGMOID_PROBES], np.float64)
    canonical = pava.sigmoid(probes)
    with np.errstate(over="ignore"):
        naive = 1.0 / (1.0 + np.exp(-probes))
    differing = [float(probes[index]) for index in range(probes.size)
                 if canonical[index] != naive[index]]
    assert differing, ("the naive form is bit-identical on this grid today; "
                       "re-measure the probe set before trusting it")
    assert -4.0 in differing


LANDMINE_SOURCE = (
    "from scipy.special import expit\n"
    "import scipy.special\n"
    "def f(x):\n"
    "    return expit(x) + scipy.special.expit(x)\n")


def _production_sources() -> tuple:
    return tuple(
        path for path in _h3_support.source_files(_h3_support.HOLO3_ROOT)
        if "conversion_docs" not in path.parts and "tests" not in path.parts)


def _banned_symbol_lines(source: str, filename: str) -> list[int]:
    hits: list[int] = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        if isinstance(node, ast.ImportFrom) and any(
                alias.name == BANNED_CALIBRATION_SYMBOL
                for alias in node.names):
            hits.append(node.lineno)
        elif isinstance(node, ast.Attribute) and (
                node.attr == BANNED_CALIBRATION_SYMBOL):
            hits.append(node.lineno)
        elif isinstance(node, ast.Name) and (
                node.id == BANNED_CALIBRATION_SYMBOL):
            hits.append(node.lineno)
    return hits


def test_the_expit_detector_still_detects_before_it_reports_a_clean_tree():
    assert _banned_symbol_lines(LANDMINE_SOURCE, "<landmine>") == [1, 4, 4]


def test_no_module_under_holo3_reaches_for_scipy_special_expit():
    checks = _h3_support.Checks("scipy.special.expit ban")
    scanned = 0
    for path in _production_sources():
        scanned += 1
        hits = _banned_symbol_lines(path.read_text(), str(path))
        checks.check(f"{path.name} free of {BANNED_CALIBRATION_SYMBOL}",
                     not hits, f"lines {hits}")
    assert scanned > 20
    checks.assert_clean()


def test_pava_nodes_are_isotonic_with_the_one_over_n_plus_two_clamp():
    rng = np.random.default_rng(20260829)
    scores = rng.normal(size=400)
    labels = rng.random(400) < 0.4
    knots, probabilities = pava._pava_nodes(scores, labels)
    assert knots.size == probabilities.size >= 2
    assert bool(np.all(np.diff(knots) > 0))
    assert bool(np.all(np.diff(probabilities) > 0))
    floor = 1.0 / (scores.size + 2.0)
    assert probabilities.min() >= floor
    assert probabilities.max() <= 1.0 - floor


def test_pava_nodes_leave_an_already_monotone_ladder_alone():
    rng = np.random.default_rng(20260829)
    scores = rng.normal(size=MONOTONE_LADDER_SAMPLES)
    ranks = np.argsort(np.argsort(scores))
    labels = ranks >= MONOTONE_LADDER_SAMPLES // 2
    knots, probabilities = pava._pava_nodes(scores, labels)
    assert knots.size == 2
    assert tuple(float(value) for value in probabilities) == (
        MONOTONE_LADDER_NODES)
    again = pava._pava_nodes(np.sort(scores), np.sort(labels))
    assert np.array_equal(again[1], probabilities)


def test_pava_nodes_on_an_empty_input_return_empty_arrays():
    knots, probabilities = pava._pava_nodes(
        np.zeros(0, np.float64), np.zeros(0, bool))
    assert knots.size == 0 and probabilities.size == 0


def test_calibration_probability_is_the_interpolation_of_the_nodes():
    rng = np.random.default_rng(20260829)
    scores = rng.normal(size=500)
    labels = (scores + rng.normal(scale=0.5, size=500)) > 0
    knots, probabilities = pava._pava_nodes(scores, labels)
    query = rng.normal(size=200) * 3.0
    got = pava.calibration_probability(query, knots, probabilities)
    assert np.array_equal(got, np.interp(query, knots, probabilities))
    assert float(pava.calibration_probability(
        np.asarray([-1e6]), knots, probabilities)[0]) == probabilities[0]
    assert float(pava.calibration_probability(
        np.asarray([1e6]), knots, probabilities)[0]) == probabilities[-1]
    llr = pava.calibration_llr(query, knots, probabilities)
    assert np.array_equal(llr, np.log(got / (1.0 - got)))


# 2026-09-20: a starved window's stored row reaches this seam with a
# degenerate node set (knots and probabilities all zero), which
# interpolated to an infinite LLR and came back as NaN through the loss.
# The floor is 018.7 at this seam, not a warning filter.
def test_a_degenerate_node_set_still_gives_a_bounded_finite_llr():
    assert pava.CAL_PROBABILITY_FLOOR == 1.0 / (
        1.0 + float(np.exp(CAL_FLOOR_LOG_ODDS)))
    knots = np.zeros(2, np.float32)
    scores = np.asarray([-1.0, 0.0, 1.0], np.float64)
    labels = np.zeros(scores.size, np.float64)
    for probabilities, sign in ((np.zeros(2, np.float32), -1.0),
                                (np.ones(2, np.float32), 1.0)):
        llr = pava.calibration_llr(scores, knots, probabilities)
        assert bool(np.all(np.isfinite(llr)))
        assert bool(np.allclose(llr, sign * CAL_FLOOR_LOG_ODDS, atol=1e-6))
        assert np.isfinite(pava._binary_logloss(llr, labels))


def test_clamp_for_is_log1p_of_the_search_label_count():
    for count in (0, 1, 2, 10, 100, 4096):
        assert pava.clamp_for(count) == float(np.log1p(count))


def test_class_balanced_weights_give_every_present_class_the_same_mass():
    states = np.array([0, 0, 1, 2, 2, 2, 6], np.int64)
    weights = pava.class_balanced_weights(states)
    assert weights.shape == states.shape
    assert float(weights.sum()) == pytest.approx(float(states.size), abs=1e-9)
    per_class = {int(state): float(weights[states == state].sum())
                 for state in np.unique(states)}
    assert set(per_class) == {0, 1, 2, 6}
    for total in per_class.values():
        assert total == pytest.approx(states.size / len(per_class), abs=1e-9)
    assert float(weights[0]) == float(weights[1])
    assert float(weights[3]) < float(weights[2])


def test_class_balanced_weights_survive_empty_and_single_class_inputs():
    empty = pava.class_balanced_weights(np.zeros(0, np.int64))
    assert empty.size == 0
    single = pava.class_balanced_weights(np.zeros(5, np.int64))
    assert np.array_equal(single, np.ones(5))


def test_solve_offset_drives_the_expected_count_onto_the_label_count():
    rng = np.random.default_rng(20260829)
    llr = rng.normal(scale=3.0, size=200)
    labels = rng.random(200) < 0.5
    weights = rng.uniform(0.1, 1.0, size=200)
    offset = pava._solve_offset(llr, labels, weights)
    assert abs(offset) < CTX_OFFSET_LIMIT
    residual = float(np.sum(weights * pava.sigmoid(llr + offset))
                     - np.sum(weights * labels))
    assert abs(residual) < 1e-9
    bracket = pava._solve_offset(llr + 1e-6, labels, weights)
    assert abs(bracket - offset) < 1e-3


def test_solve_offset_returns_the_bracket_ends_when_no_root_exists():
    rng = np.random.default_rng(20260829)
    llr = rng.normal(size=64)
    weights = np.ones(64)
    assert pava._solve_offset(
        llr, np.ones(64, bool), weights) == CTX_OFFSET_LIMIT
    assert pava._solve_offset(
        llr, np.zeros(64, bool), weights) == -CTX_OFFSET_LIMIT


def test_ordered_context_offsets_are_non_increasing_across_the_nine_bins():
    rng = np.random.default_rng(20260829)
    n_sites = 900
    llr = rng.normal(scale=2.0, size=n_sites)
    bins = rng.integers(0, N_CONTEXT_BINS, size=n_sites).astype(np.int64)
    labels = (llr - 0.4 * bins + rng.normal(size=n_sites)) > 0
    weights = np.ones(n_sites)
    offsets = pava._ordered_context_offsets(llr, bins, labels, weights)
    assert offsets.shape == (N_CONTEXT_BINS,)
    assert bool(np.all(np.diff(offsets) <= 0.0))
    assert bool(np.all(np.abs(offsets) <= CTX_OFFSET_LIMIT))


def test_an_empty_context_bin_falls_back_to_its_two_prior_observations():
    rng = np.random.default_rng(20260829)
    n_sites = 400
    llr = rng.normal(scale=2.0, size=n_sites)
    bins = np.full(n_sites, 3, np.int64)
    labels = llr > 0
    offsets = pava._ordered_context_offsets(llr, bins, labels,
                                            np.ones(n_sites))
    assert offsets.shape == (N_CONTEXT_BINS,)
    assert float(offsets[0]) == float(offsets[1]) == float(offsets[2])
    assert bool(np.all(np.isfinite(offsets)))


def test_the_three_loglosses_are_one_function_in_three_spellings():
    rng = np.random.default_rng(20260829)
    llr = rng.normal(scale=4.0, size=400)
    labels = (llr + rng.normal(size=400)) > 0
    weights = rng.uniform(0.2, 2.0, size=400)
    assert pava._logloss(llr, labels, weights) == pytest.approx(
        pava._binary_logloss(llr, labels, weights), rel=1e-12)
    assert pava.probability_logloss(
        pava.sigmoid(llr), labels) == pytest.approx(
            pava._binary_logloss(llr, labels), rel=1e-12)
    assert pava._binary_logloss(llr, labels) < 0.5 * pava._binary_logloss(
        -llr, labels)

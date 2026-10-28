from __future__ import annotations

import numpy as np
import pytest

from holo.core.channel import states_to_planes
from holo.qualification.color_synthetic import (
    ColorChannelParameters,
    PlaneParameters,
    render_color_scan,
)
from holo.receive import color_detect
from paperholo import acquire as historical


def _state_cloud(
    n_states: int,
    per_state: int,
    *,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    states = np.repeat(np.arange(n_states, dtype=np.uint8), per_state)
    bits = states_to_planes(states)
    # Reflected R/G/B: corresponding ink lowers the channel.  State-dependent
    # covariance keeps the differential test sensitive to QDA shrinkage.
    means = 0.87 - 0.52 * bits
    samples = np.empty((states.size, 3), dtype=np.float64)
    for state in range(n_states):
        selected = states == state
        base = np.asarray((
            (0.0030 + state * 0.00008, 0.00035, 0.00020),
            (0.00035, 0.0040 + state * 0.00006, 0.00030),
            (0.00020, 0.00030, 0.0050 + state * 0.00004),
        ))
        samples[selected] = rng.multivariate_normal(
            means[selected][0], base, size=int(selected.sum()))
    return samples, states


def _historical_anchor_zero(
    score_nodes: np.ndarray,
    probability_nodes: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    insertion = int(np.searchsorted(score_nodes, 0.0))
    if (
        0 < insertion < score_nodes.size
        and score_nodes[insertion - 1] < 0.0 < score_nodes[insertion]
        and probability_nodes[insertion - 1] <= 0.5
        <= probability_nodes[insertion]
    ):
        return (
            np.insert(score_nodes, insertion, 0.0),
            np.insert(probability_nodes, insertion, 0.5),
        )
    return score_nodes, probability_nodes


def test_blind_registration_halo_detector_is_exactly_historical() -> None:
    rng = np.random.default_rng(202607283)
    means = rng.beta(1.7, 2.3, size=(37, 29))
    expected_bits, expected_llr = historical.cell_bits_blind(means)
    bits, llr = color_detect.blind_component_bits(means)
    np.testing.assert_array_equal(bits, expected_bits)
    np.testing.assert_array_equal(llr, expected_llr)


@pytest.mark.parametrize("n_states", (7, 8))
def test_qda_fit_and_scores_differential_to_paperholo(
    n_states: int,
) -> None:
    features, states = _state_cloud(n_states, 47, seed=202607260 + n_states)
    expected = historical.fit_qda(
        features, states, n_classes=n_states)
    got = color_detect.fit_equal_prior_qda(
        features, states, n_states=n_states)

    np.testing.assert_array_equal(got.means, expected["mu"])
    np.testing.assert_array_equal(
        got.log_determinants, expected["logdet"])
    np.testing.assert_array_equal(
        got.class_counts, expected["n_per_class"])
    for got_factor, expected_factor in zip(
        got.cholesky, expected["chol"]
    ):
        np.testing.assert_array_equal(got_factor, expected_factor)
    assert got.warnings == tuple(expected["warnings"])
    assert got.clipped_planes == tuple(sorted(expected["clip_levels"]))
    assert got.degenerate is expected["degenerate"]

    probes = features[::7] + np.asarray((0.013, -0.009, 0.021))
    np.testing.assert_array_equal(
        color_detect.qda_log_scores(got, probes),
        historical.qda_log_densities(expected, probes),
    )
    if n_states == 7:
        old_scores = historical.qda_log_densities(expected, probes)
        np.testing.assert_array_equal(
            color_detect.cmy7_relative_scores(got, probes),
            old_scores[:, 1:] - old_scores[:, :1],
        )
    else:
        np.testing.assert_array_equal(
            color_detect.cmy8_raw_llrs(got, probes),
            historical.qda_level_llrs(expected, probes).T,
        )


def test_balanced_unique_cmy8_pava_preserves_historical_path() -> None:
    features, states = _state_cloud(8, 53, seed=202607278)
    detector = color_detect.fit_cmy8_detector(
        features,
        states,
        features,
        states,
    )
    old_model = historical.fit_qda(features, states)
    old_raw = historical.qda_level_llrs(old_model, features).T

    expected_llrs = np.empty_like(old_raw)
    for plane in range(3):
        labels = ((states >> plane) & 1).astype(np.float64)
        score_nodes, probability_nodes = historical.pava_calibrate(
            old_raw[:, plane], labels)
        score_nodes, probability_nodes = _historical_anchor_zero(
            score_nodes, probability_nodes)
        calibration = detector.calibrations[plane]
        np.testing.assert_allclose(
            calibration.score_nodes, score_nodes, rtol=0.0, atol=5e-13)
        np.testing.assert_array_equal(
            calibration.probability_nodes, probability_nodes)
        expected_llrs[:, plane] = historical.apply_calibration(
            old_raw[:, plane], score_nodes, probability_nodes)

    np.testing.assert_allclose(
        detector.llrs(features), expected_llrs, rtol=0.0, atol=5e-13)
    assert detector.pava_in_sample is True
    assert detector.calibration_labels == features.shape[0]


def test_cmy8_pava_pools_ties_before_fitting_and_is_permutation_stable(
) -> None:
    scores = np.repeat(
        np.asarray((-2.0, -0.5, 0.0, 1.5, 4.0)), (17, 31, 23, 29, 19))
    labels = (
        (np.arange(scores.size, dtype=np.int64) * 17 + 3) % 5 < 2
    ).astype(np.float64)
    expected = color_detect._pava_map(scores, labels)
    assert np.all(np.diff(expected.score_nodes) > 0.0)

    rng = np.random.default_rng(202607291)
    for _ in range(20):
        order = rng.permutation(scores.size)
        got = color_detect._pava_map(scores[order], labels[order])
        np.testing.assert_array_equal(got.score_nodes, expected.score_nodes)
        np.testing.assert_array_equal(
            got.probability_nodes, expected.probability_nodes)


def test_cmy8_pava_neutralizes_the_skewed_dust_prior_without_wire_changes(
) -> None:
    # CMY8 word furniture owns W/CM.  The six dust states consequently have
    # C/M support 3/6 each but Y support 4/6.  A constant score axis contains
    # no component evidence and must map to zero for all three planes.
    dust_states = np.tile(
        np.asarray((1, 2, 4, 5, 6, 7), dtype=np.uint8), 50)
    scores = np.zeros(dust_states.size, dtype=np.float64)
    for plane in range(3):
        labels = (dust_states >> plane) & 1
        if plane == 2:
            assert int(labels.sum()) == 200
        calibration = color_detect._pava_map(scores, labels)
        np.testing.assert_array_equal(
            calibration.score_nodes, np.asarray((0.0,)))
        np.testing.assert_array_equal(
            calibration.probability_nodes, np.asarray((0.5,)))
        np.testing.assert_array_equal(
            calibration.llrs(np.asarray((-1.0, 0.0, 1.0))),
            np.zeros(3),
        )


def test_zero_anchor_preserves_qda_decision_sign_in_a_perfect_gap() -> None:
    features, states = _state_cloud(8, 50, seed=202607279)
    detector = color_detect.fit_cmy8_detector(
        features, states, features, states)
    for calibration in detector.calibrations:
        zero = np.flatnonzero(calibration.score_nodes == 0.0)
        assert zero.size == 1
        assert calibration.probability_nodes[zero[0]] == 0.5
        assert calibration.llrs(np.asarray((-1e-12, 1e-12)))[0] < 0.0
        assert calibration.llrs(np.asarray((-1e-12, 1e-12)))[1] > 0.0


def test_cmy8_structural_support_has_no_historical_300_label_cliff() -> None:
    features, states = _state_cloud(8, 50, seed=202607280)
    detector = color_detect.fit_cmy8_detector(
        features,
        states,
        features[:299],
        states[:299],
    )
    assert detector.calibration_labels == 299
    assert detector.calibration_support.supported_planes == (
        True, True, True)
    assert detector.supported_planes == (True, True, True)
    assert np.any(detector.llrs(features[:17]) != 0.0)


def test_cmy8_support_sweep_is_structural_and_permutation_stable() -> None:
    dust_cycle = np.asarray((1, 2, 4, 5, 6, 7), dtype=np.uint8)
    expected = {
        2: (False, False, False),
        3: (True, True, True),
        8: (True, True, True),
        50: (True, True, True),
    }
    rng = np.random.default_rng(202607293)
    for repeats, supported in expected.items():
        states = np.tile(dust_cycle, repeats)
        reference = color_detect.qualify_cmy8_calibration_support(states)
        assert reference.n_labels == states.size
        assert reference.supported_planes == supported
        for _ in range(7):
            got = color_detect.qualify_cmy8_calibration_support(
                states[rng.permutation(states.size)])
            assert got == reference


def test_cmy8_support_requires_nuisance_state_diversity() -> None:
    # C has ample labels in both binary classes, but its zero class contains
    # only state W.  A marginal C score calibrated on that single nuisance
    # state is not structurally identified.
    states = np.concatenate((
        np.repeat(np.uint8(0), 40),
        np.repeat(np.uint8(1), 20),
        np.repeat(np.uint8(3), 20),
    ))
    support = color_detect.qualify_cmy8_calibration_support(states)
    assert support.components[0].class_counts == (40, 40)
    assert support.components[0].qualified_state_counts == (1, 2)
    assert support.components[0].supported is False
    assert support.components[0].reason == "state_diversity:0"


def test_cmy8_unsupported_component_is_an_exact_local_erasure() -> None:
    features, states = _state_cloud(8, 50, seed=202607294)
    calibration_counts = {
        1: 12,
        2: 3,
        5: 12,
        7: 12,
    }
    selected = np.concatenate(tuple(
        np.flatnonzero(states == state)[:count]
        for state, count in calibration_counts.items()
    ))
    detector = color_detect.fit_cmy8_detector(
        features,
        states,
        features[selected],
        states[selected],
    )
    assert detector.calibration_support.supported_planes == (
        False, True, True)
    assert detector.supported_planes == (False, True, True)
    assert detector.unsupported_reasons == (
        "class_labels:0", None, None)

    llrs = detector.llrs(features)
    np.testing.assert_array_equal(llrs[:, 0], np.zeros(features.shape[0]))
    expected = states_to_planes(states)
    assert np.mean((llrs[:, 1:] > 0.0) == expected[:, 1:]) > 0.995
    assert np.any(llrs[:, 1:] != 0.0)


def test_degenerate_qda_clips_only_cmy8_marginals_not_cmy7_scores() -> None:
    features, states = _state_cloud(8, 40, seed=202607281)
    selected = states != 7
    # Keep the total count above eight while omitting class 7.
    model8 = color_detect.fit_equal_prior_qda(
        features[selected], states[selected], n_states=8)
    assert model8.degenerate
    llrs = color_detect.cmy8_raw_llrs(model8, features[:20])
    assert np.max(np.abs(llrs)) <= color_detect.DEGENERATE_LLR_CLIP

    model7 = color_detect.fit_equal_prior_qda(
        features[selected], states[selected], n_states=7)
    relative = color_detect.cmy7_relative_scores(model7, features[:20])
    assert np.isfinite(relative).all()
    assert np.max(np.abs(relative)) > color_detect.DEGENERATE_LLR_CLIP


def test_cmy8_collapsed_plane_is_zero_but_other_planes_remain_usable() -> None:
    features, states = _state_cloud(8, 50, seed=202607284)
    # States 3 and 7 differ only in Y.  Make their observed distributions
    # identical so Y is explicitly marked collapsed.
    features[states == 7] = features[states == 3]
    detector = color_detect.fit_cmy8_detector(
        features, states, features, states)
    assert 2 in detector.qda.clipped_planes
    final = detector.llrs(features)
    np.testing.assert_array_equal(final[:, 2], np.zeros(final.shape[0]))
    expected = states_to_planes(states)
    assert np.mean((final[:, :2] > 0.0) == expected[:, :2]) > 0.995
    assert np.any(final[:, :2] != 0.0)


def test_cmy8_globally_degenerate_qda_emits_no_evidence() -> None:
    features, states = _state_cloud(8, 50, seed=202607292)
    selected = states != 7
    detector = color_detect.fit_cmy8_detector(
        features[selected],
        states[selected],
        features[selected],
        states[selected],
    )
    assert detector.qda.degenerate
    np.testing.assert_array_equal(
        detector.llrs(features[:37]), np.zeros((37, 3)))


def test_synthetic_color_channel_drives_cmy7_and_cmy8_detector_outputs() -> None:
    height, width = 32, 40
    state_grid = (
        np.arange(height * width, dtype=np.uint16).reshape(height, width) % 8
    ).astype(np.uint8)
    source_cmy = states_to_planes(state_grid).astype(np.float64)
    scan = render_color_scan(
        source_cmy,
        ColorChannelParameters(
            planes=(
                PlaneParameters(contrast=0.78, gamma=1.05),
                PlaneParameters(contrast=0.70, gamma=1.10),
                PlaneParameters(contrast=0.62, gamma=1.14),
            ),
            subtractive_rgb=(
                (0.72, 0.05, 0.03),
                (0.04, 0.68, 0.04),
                (0.03, 0.06, 0.61),
            ),
            paper_rgb=(0.94, 0.92, 0.89),
            noise_std_rgb=(0.012, 0.014, 0.016),
            seed=20260726,
        ),
    )
    rgb = np.ascontiguousarray(scan.rgb, dtype=np.float64)
    if rgb.size and float(rgb.max()) > 1.5:
        rgb = rgb / 255.0
    features = rgb.reshape(-1, 3)
    states = state_grid.ravel()

    detector8 = color_detect.fit_cmy8_detector(
        features, states, features, states)
    expected_bits = states_to_planes(states)
    decoded_bits = (detector8.llrs(features) > 0.0).astype(np.uint8)
    assert np.mean(decoded_bits == expected_bits) > 0.995

    legal = states != 7
    model7 = color_detect.fit_equal_prior_qda(
        features[legal], states[legal], n_states=7)
    relative = color_detect.cmy7_relative_scores(
        model7, features[legal])
    scores = np.column_stack((np.zeros(relative.shape[0]), relative))
    assert np.mean(np.argmax(scores, axis=1) == states[legal]) > 0.995


@pytest.mark.parametrize(
    ("call", "match"),
    (
        (
            lambda: color_detect.fit_equal_prior_qda(
                np.zeros((8, 3)), np.arange(8), n_states=6),
            "n_states",
        ),
        (
            lambda: color_detect.fit_equal_prior_qda(
                np.zeros((8, 3)), np.arange(8) + 1, n_states=8),
            "must lie",
        ),
    ),
)
def test_detector_boundary_validation(call, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        call()

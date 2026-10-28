"""Focused numerical and scheduling contracts for the E024 feedback loop."""
from __future__ import annotations

import copy
import hashlib
import json
import pickle
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
E024_EXP = ROOT / "experiments/024-feedback-receiver"
E023B_EXP = ROOT / "experiments/023b-integrated-receiver"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(E024_EXP))
sys.path.insert(0, str(E023B_EXP))

from paperholo import (compose, feedback, feedbackstate, ldpc,  # noqa: E402
                       payloaddec, receiver)
from paperholo.feedbackstate import (  # noqa: E402
    EvidenceRevision,
    FeedbackConfig,
    LabelUse,
    PROFILE_COMBINED,
    PROFILE_RECAL,
    PROFILE_REFINE,
)
from paperholo.formats import FormatDescriptor  # noqa: E402

import test_e023 as t23  # noqa: E402
import test_e023b_session as e23b_session  # noqa: E402
import merge_e023b  # noqa: E402
import run_e024  # noqa: E402


def _demote_one_certificate(
    baseline: receiver.ReceiverSession,
) -> tuple[receiver.ReceiverSession, tuple[int, int, int]]:
    """Produce a valid E023b baseline with one unresolved former success."""
    working = baseline.fork()
    position, parent = next(
        (position, row)
        for position, row in enumerate(working.attempts)
        if row.certified_new and row.stage == "scan"
    )
    key = (int(parent.page), *map(int, parent.tile_yx))
    working.attempts[position] = replace(
        parent,
        state="attempted_failed",
        certified_new=False,
        syndrome_ok=False,
        crc_ok=False,
    )
    outcome = working.decode.tiles[key]
    outcome.state = "attempted_failed"
    outcome.user_bits = None
    outcome.certified_by = ""
    outcome.n_iters = 0
    outcome.divergence = {}
    working.validate_invariants()
    return working, key


@pytest.fixture(scope="module")
def compact_baselines(tmp_path_factory):
    """One small but genuine E023b scan, plus a coherently demoted branch."""
    tmp_path = tmp_path_factory.mktemp("e024_algorithm")
    descriptor = FormatDescriptor(
        "e024-algorithm-test",
        b"paper-store/e024-algorithm-test",
        3,
        "kcell-c3",
        (120, 120),
        ldpc_rate="r0550",
    )
    rng = np.random.default_rng(2401)
    values, _user, _framed = t23._coded_page(descriptor, rng)
    image = t23._render_cells(values, rng)
    placement = t23._placed_window(
        np.asarray(values.shape),
        0,
        0,
        *values.shape,
        origin_px=(t23.PITCH / 2 - 0.5, t23.PITCH / 2 - 0.5),
    )
    row = t23._scan_row(tmp_path, "s000", image, [placement])
    upstream = payloaddec.load_e022_session(
        t23._write_state(
            tmp_path, t23._session_payload(descriptor, [row])
        )
    )
    baseline = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    stored_image = receiver.load_image(upstream.scans[0].source_path)
    baseline, counts = receiver.apply_scan(
        baseline,
        e23b_session._record(
            descriptor, upstream.scans[0], stored_image),
    )
    assert counts["newly_certified"] == 4

    full_path = tmp_path / "baseline_full.pkl"
    receiver.save_session(full_path, baseline)
    demoted, demoted_key = _demote_one_certificate(baseline)
    demoted_path = tmp_path / "baseline_demoted.pkl"
    receiver.save_session(demoted_path, demoted)
    return {
        "baseline": baseline,
        "full_path": full_path,
        "demoted": demoted,
        "demoted_path": demoted_path,
        "demoted_key": demoted_key,
    }


def _spatial_labels(
    values: np.ndarray,
    page_yx: np.ndarray,
    *,
    block_cells: int = 4,
) -> feedback.WindowLabels:
    """Whole-block train/validation labels with equal block influence."""
    values = np.asarray(values, np.uint8).ravel()
    page_yx = np.asarray(page_yx, np.int64)
    local = page_yx - page_yx.min(axis=0)
    by = local[:, 0] // block_cells
    bx = local[:, 1] // block_cells
    block_ids = by * 10_000 + bx
    validation = ((by + 2 * bx) % 4) == 0
    weights = np.zeros(values.size, np.float64)
    weights[~validation] = feedback._block_weights(
        block_ids[~validation]
    )
    weights[validation] = feedback._block_weights(
        block_ids[validation]
    )
    return feedback.WindowLabels(
        row_positions=np.arange(values.size, dtype=np.int64),
        values=values,
        validation=validation,
        weights=weights,
        is_pilot=np.zeros(values.size, bool),
        block_ids=block_ids.astype(np.int64),
        payload_indices=np.arange(values.size, dtype=np.int64),
        certificate_ids=tuple("fixture-certificate" for _ in values),
        tile_keys=tuple((0, 0, 0) for _ in values),
    )


def test_weighted_pava_is_monotone_weighted_and_permutation_stable() -> None:
    scores = np.array([0, 0, 1, 1, 2, 2], np.float64)
    labels = np.array([0, 1, 1, 1, 0, 0], np.uint8)
    weights = np.array([1, 3, 1, 1, 2, 2], np.float64)

    nodes_s, nodes_p = feedback.weighted_pava_calibrate(
        scores, labels, weights
    )
    # The high-score zero block pools backward through both predecessors.
    assert np.allclose(nodes_s, [1.0])
    assert np.allclose(nodes_p, [0.5])

    scores = np.array([0, 1, 2, 3], np.float64)
    labels = np.array([0, 1, 0, 1], np.uint8)
    weights = np.ones(4, np.float64)
    want_s = np.array([0.0, 1.5, 3.0])
    want_p = np.array([1 / 3, 1 / 2, 2 / 3])
    got_s, got_p = feedback.weighted_pava_calibrate(
        scores, labels, weights
    )
    assert np.allclose(got_s, want_s)
    assert np.allclose(got_p, want_p)
    assert np.all(np.diff(got_p) > 0.0)

    order = np.array([3, 0, 2, 1])
    perm_s, perm_p = feedback.weighted_pava_calibrate(
        scores[order], labels[order], weights[order]
    )
    assert np.array_equal(perm_s, got_s)
    assert np.array_equal(perm_p, got_p)

    with pytest.raises(ValueError, match="invalid"):
        feedback.weighted_pava_calibrate(
            np.array([0.0, np.nan]), np.array([0, 1]), np.ones(2)
        )


def _replayed_payload(
    emission: payloaddec.WindowEmission,
    baseline: receiver.ReceiverSession,
) -> tuple[np.ndarray, np.ndarray]:
    """Reconstruct persisted payload evidence from persisted detector state."""
    physical_logits = feedback._physical_logits(emission)
    assert physical_logits is not None
    page_yx = np.asarray(emission.page_cells_yx, np.int64)
    payload_map = compose.payload_index_map(
        baseline.decode.spec, baseline.decode.seed
    )
    payload_index = payload_map[page_yx[:, 0], page_yx[:, 1]]
    selected = payload_index >= 0
    keystream = compose.payload_keystream(
        baseline.decode.spec, baseline.decode.seed, emission.page
    )
    payload_llr = (
        physical_logits[selected]
        * (
            1.0
            - 2.0
            * keystream[
                page_yx[selected, 0], page_yx[selected, 1]
            ].astype(np.float64)
        )
    ).astype(np.float32)
    return payload_index[selected].astype(np.int64), payload_llr


def test_detector_constructors_finalize_payload_from_stored_scores() -> None:
    descriptor = FormatDescriptor(
        "e024-dense-test",
        b"paper-store/e024-dense-test",
        3,
        "kcell-c3",
        (120, 120),
        ldpc_rate="r0550",
    )
    baseline = receiver.ReceiverSession.create(
        descriptor, (0,), 1600.0
    )
    height = width = 24
    y0 = x0 = 24
    placed = t23._placed_window(
        np.asarray(descriptor.page_cells_yx),
        y0,
        x0,
        height,
        width,
        origin_px=(t23.PITCH / 2 - 0.5, t23.PITCH / 2 - 0.5),
    )
    yy, xx = np.meshgrid(
        np.arange(height), np.arange(width), indexing="ij"
    )
    physical = ((yy + xx) % 2).astype(np.uint8).ravel()
    rng = np.random.default_rng(2402)
    row_bias = np.repeat(np.linspace(-28.0, 28.0, height), width)
    means = (
        190.0
        - 105.0 * physical
        + row_bias
        + rng.normal(0.0, 4.0, physical.size)
    )
    labels = _spatial_labels(physical, placed.page_cells_yx)

    # Generation zero has retained the pixels but supplies no useful
    # confidence: every physical cell is interpreted as p=0.5.
    parent = payloaddec.WindowEmission(
        placement_ordinal=0,
        page=0,
        payload_index=np.arange(physical.size, dtype=np.int64),
        payload_llr=np.zeros(physical.size, np.float32),
        heldout_logloss=float(np.log(2.0)),
        n_train_labels=int(labels.train.sum()),
        n_heldout=int(labels.validation.sum()),
        region_index=0,
        page_cells_yx=np.asarray(placed.page_cells_yx, np.int32).copy(),
        raw_means=means.astype(np.float32),
        scores=np.zeros(physical.size, np.float32),
        calibration_score_nodes=np.array([0.0]),
        calibration_probability_nodes=np.array([0.5]),
    )
    label_field = feedback.LabelField(
        values={
            0: np.full(descriptor.page_cells_yx, -1, np.int8)
        },
        certificate_ids={(0, 0, 0): "fixture-certificate"},
        payload_indices={},
    )
    config = FeedbackConfig(
        block_cells=4,
        min_payload_train=64,
        min_payload_validation=32,
        min_label_blocks=4,
    )

    emission, metrics, uses = feedback.fit_detector_revision(
        placed,
        parent,
        means,
        labels,
        label_field,
        baseline,
        config,
    )
    assert emission is not None
    assert metrics["eligible"] and metrics["adopted"]
    assert metrics["candidate_validation_logloss"] < 0.25
    assert (
        metrics["candidate_validation_logloss"]
        < metrics["parent_validation_logloss"] - 0.4
    )
    assert metrics["n_label_blocks"] == 36
    assert len(uses) == 1 and uses[0].n_sites == physical.size
    assert emission.detector_profile == feedback.DETECTOR_PROFILE
    assert np.max(np.abs(feedback._physical_logits(emission))) <= (
        config.context_clip + 1e-12
    )
    predicted = feedback._physical_logits(emission) > 0.0
    assert np.mean(
        predicted[labels.validation] == physical[labels.validation]
    ) > 0.98

    dense_index, dense_llr = _replayed_payload(emission, baseline)
    assert np.array_equal(emission.payload_index, dense_index)
    assert np.array_equal(emission.payload_llr, dense_llr)
    dense_scores64, _mid, _spread = feedback._scores_from_means(means)
    assert np.any(
        dense_scores64
        != np.asarray(emission.scores, np.float64)
    )
    _legacy_index, legacy_dense_llr = _replayed_payload(
        replace(emission, scores=dense_scores64), baseline
    )
    # This is the real-sheet failure mode: constructing payload LLRs from
    # pre-quantization float64 scores does not reproduce the stored state.
    assert not np.array_equal(legacy_dense_llr, dense_llr)

    fixed, fixed_metrics = feedback._fixed_detector_revision(
        placed,
        emission,
        parent,
        means,
        labels,
        label_field,
        baseline,
        config,
    )
    assert fixed is not None
    assert fixed_metrics["eligible"] and fixed_metrics["adopted"]
    fixed_index, fixed_llr = _replayed_payload(fixed, baseline)
    assert np.array_equal(fixed.payload_index, fixed_index)
    assert np.array_equal(fixed.payload_llr, fixed_llr)
    fixed_scores, _fixed_logits = (
        feedback._generation0_detector_logits(
            emission, placed.page_cells_yx, means
        )
    )
    assert fixed_scores.dtype == np.float32
    assert np.array_equal(fixed_scores, fixed.scores)


def test_generation_zero_detector_replays_persisted_scores_exactly(
    compact_baselines,
) -> None:
    baseline = compact_baselines["baseline"]
    payload_map = compose.payload_index_map(
        baseline.decode.spec, baseline.decode.seed)
    saw_quantized_source_difference = False
    replayed = 0
    for scan in baseline.scans:
        for emission in scan.window_evidence:
            if (emission.refused
                    or emission.calibration_score_nodes.size == 0):
                continue
            replayed += 1
            scores, logits = feedback._generation0_detector_logits(
                emission, emission.page_cells_yx, emission.raw_means)
            stored_logits = feedback._physical_logits(emission)
            assert stored_logits is not None
            assert np.array_equal(scores, emission.scores)
            assert np.array_equal(logits, stored_logits)

            page_yx = np.asarray(emission.page_cells_yx, np.int64)
            pidx = payload_map[page_yx[:, 0], page_yx[:, 1]]
            selected = pidx >= 0
            keystream = compose.payload_keystream(
                baseline.decode.spec, baseline.decode.seed,
                int(emission.page))
            payload_llr = (
                logits[selected]
                * (1.0 - 2.0 * keystream[
                    page_yx[selected, 0],
                    page_yx[selected, 1]].astype(np.float64))
            ).astype(np.float32)
            assert np.array_equal(
                pidx[selected].astype(np.int64),
                emission.payload_index)
            assert np.array_equal(payload_llr, emission.payload_llr)

            mid = float(emission.diagnostics["mid"])
            spread = float(emission.diagnostics["spread"])
            reconstructed = np.asarray(
                (
                    mid
                    - np.asarray(emission.raw_means, np.float64))
                / spread,
                np.float32)
            saw_quantized_source_difference |= not np.array_equal(
                reconstructed, emission.scores)
    assert replayed
    assert saw_quantized_source_difference


def test_physical_logits_replays_base_clip_before_context_exactly() -> None:
    page_yx = np.stack(
        np.meshgrid(np.arange(3), np.arange(3), indexing="ij"),
        axis=-1,
    ).reshape(-1, 2)
    raw_probability = 0.999999
    raw_logit = np.log(raw_probability / (1.0 - raw_probability))
    tau = np.zeros(9, np.float64)
    tau[8] = -3.0
    emission = payloaddec.WindowEmission(
        placement_ordinal=0,
        page=0,
        payload_index=np.arange(page_yx.shape[0], dtype=np.int64),
        payload_llr=np.zeros(page_yx.shape[0], np.float32),
        heldout_logloss=0.1,
        n_train_labels=8,
        n_heldout=1,
        region_index=0,
        page_cells_yx=page_yx.astype(np.int32),
        raw_means=np.zeros(page_yx.shape[0], np.float32),
        scores=np.zeros(page_yx.shape[0], np.float32),
        calibration_score_nodes=np.array([0.0]),
        calibration_probability_nodes=np.array([raw_probability]),
        detector_profile=feedback.DETECTOR_PROFILE,
        diagnostics={
            "feedback_base_clip": 8.0,
            "feedback_context_tau": tuple(tau),
            "feedback_context_clip": 8.0,
        },
    )

    replayed = feedback._physical_logits(emission)
    assert replayed is not None
    base = np.full(page_yx.shape[0], np.clip(raw_logit, -8.0, 8.0))
    count, valid = payloaddec.context_neighbor_counts(
        page_yx, base > 0.0
    )
    expected = base.copy()
    expected[valid] = np.clip(
        expected[valid] + tau[count[valid]], -8.0, 8.0
    )
    assert np.allclose(replayed, expected, rtol=0.0, atol=1e-12)
    assert replayed[4] == pytest.approx(5.0)
    assert np.max(np.abs(replayed)) <= 8.0
    # Without base-clip-before-context this site would incorrectly remain
    # saturated at the context cap instead of dropping from 8 to 5.
    assert raw_logit + tau[8] > 8.0


def test_owner_rank_stays_on_fixed_e023b_pilot_scale_and_can_improve(
    compact_baselines,
) -> None:
    baseline = compact_baselines["baseline"]
    scan = baseline.scans[0]
    placed = scan.result.placements[0]
    generation0 = scan.window_evidence[0]
    site_pos, expected, validation = (
        payloaddec._window_pilot_observations(
            placed, baseline.decode.spec, baseline.decode.seed
        )
    )
    assert validation.any()

    replayed_generation0 = feedback._set_comparable_owner_rank(
        generation0, placed, baseline
    )
    assert replayed_generation0.heldout_logloss == pytest.approx(
        generation0.heldout_logloss, abs=1e-14
    )

    def candidate(probability: float, dense_loss: float):
        emission = copy.deepcopy(generation0)
        emission.scores = np.zeros(
            generation0.page_cells_yx.shape[0], np.float32
        )
        emission.scores[site_pos] = np.where(
            expected > 0, 1.0, -1.0
        )
        emission.calibration_score_nodes = np.array(
            [-1.0, 0.0, 1.0], np.float64
        )
        emission.calibration_probability_nodes = np.array(
            [1.0 - probability, 0.5, probability], np.float64
        )
        emission.context_fit = None
        emission.detector_profile = feedback.DETECTOR_PROFILE
        emission.heldout_logloss = dense_loss
        emission.diagnostics = {
            "feedback_base_clip": 8.0,
            "feedback_context_tau": tuple(np.zeros(9)),
            "feedback_context_clip": 8.0,
        }
        return emission

    weak = feedback._set_comparable_owner_rank(
        candidate(0.65, 0.01), placed, baseline
    )
    strong_source = candidate(0.9999, 0.20)
    strong = feedback._set_comparable_owner_rank(
        strong_source, placed, baseline
    )
    manual = payloaddec._logistic_logloss(
        feedback._physical_logits(strong_source)[site_pos[validation]],
        expected[validation],
    )
    assert strong.heldout_logloss == pytest.approx(manual)
    assert strong.diagnostics["feedback_owner_policy"] == (
        "fixed-pilot-validation-v1"
    )
    assert strong.diagnostics["feedback_dense_heldout_logloss"] == (
        pytest.approx(0.20)
    )
    assert strong.heldout_logloss < weak.heldout_logloss
    assert strong.heldout_logloss < generation0.heldout_logloss


def test_pose_refinement_recovers_subcell_shift_and_checks_replay() -> None:
    height = width = 24
    pixel_pitch = 8
    yy, xx = np.meshgrid(
        np.arange(height), np.arange(width), indexing="ij"
    )
    physical = ((yy + xx) % 2).astype(np.uint8)
    image = np.where(
        np.kron(physical, np.ones((pixel_pitch, pixel_pitch))) > 0,
        55.0,
        205.0,
    )
    image = ndimage.gaussian_filter(image, 0.8)
    filtered = ndimage.uniform_filter(image, size=6, mode="nearest")
    crop = payloaddec.RegionCrop(
        y0=0,
        x0=0,
        filt=filtered.astype(np.float32),
        fill=130.0,
    )

    # The generation-zero pose is shifted +1/4 cell on both axes.
    placed = t23._placed_window(
        np.asarray((120, 120)),
        0,
        0,
        height,
        width,
        origin_px=(5.5, 5.5),
    )
    local = payloaddec.local_core_cells(placed)
    raw_means = payloaddec.sample_window_means(crop, placed, local)
    labels = _spatial_labels(physical.ravel(), placed.page_cells_yx)
    labels = replace(
        labels,
        is_pilot=(np.arange(physical.size) % 4 == 0),
    )
    scores, mid, spread = feedback._scores_from_means(raw_means)
    nodes_s, nodes_p = feedback.weighted_pava_calibrate(
        scores[labels.train],
        physical.ravel()[labels.train],
        labels.weights[labels.train],
    )
    base_logits = feedback.apply_calibration(scores, nodes_s, nodes_p)
    parent = payloaddec.WindowEmission(
        placement_ordinal=0,
        page=0,
        payload_index=np.arange(raw_means.size, dtype=np.int64),
        payload_llr=np.zeros(raw_means.size, np.float32),
        heldout_logloss=float(np.log(2.0)),
        n_train_labels=int(labels.train.sum()),
        n_heldout=int(labels.validation.sum()),
        region_index=0,
        page_cells_yx=np.asarray(placed.page_cells_yx, np.int32).copy(),
        raw_means=raw_means.astype(np.float32),
        scores=scores.astype(np.float32),
        calibration_score_nodes=nodes_s,
        calibration_probability_nodes=nodes_p,
        diagnostics={"mid": mid, "spread": spread},
    )
    parent.heldout_logloss = feedback._weighted_logloss(
        base_logits[labels.validation],
        physical.ravel()[labels.validation],
        labels.weights[labels.validation],
    )
    config = FeedbackConfig(
        block_cells=4,
        min_payload_train=64,
        min_payload_validation=32,
        min_label_blocks=4,
        pose_angle_deg=0.0,
        pose_phase_cells=0.25,
        pose_phase_coarse_step_cells=0.25,
        pose_phase_fine_step_cells=0.0625,
    )

    pose, revised_means, metrics = feedback.refine_pose_on_labels(
        crop, placed, parent, labels, config
    )
    assert pose is not None and revised_means is not None
    assert metrics["eligible"] and metrics["adopted"]
    assert metrics["candidate_validation_logloss"] < (
        metrics["baseline_validation_logloss"]
    )
    assert metrics["dtheta_deg"] == 0.0
    assert -0.25 <= metrics["du_cells"] <= 0.0
    assert -0.25 <= metrics["dv_cells"] <= 0.0
    # A binary cell interior has a broad optimum: require a conservative
    # correction in at least one axis, not an unidentifiable exact center.
    assert min(metrics["du_cells"], metrics["dv_cells"]) < 0.0
    assert all(3.5 <= value <= 5.5 for value in pose.origin_yx)
    assert min(pose.origin_yx) < 5.5
    assert revised_means.shape == raw_means.shape

    corrupted_parent = copy.deepcopy(parent)
    corrupted_parent.raw_means = corrupted_parent.raw_means.copy()
    corrupted_parent.raw_means[0] += np.float32(0.25)
    with pytest.raises(
            payloaddec.FatalIntegrityError,
            match="no longer reproduces"):
        feedback.refine_pose_on_labels(
            crop, placed, corrupted_parent, labels, config
        )


def test_pose_gate_replays_e022_raw_mid_at_runtime_and_in_state(
    compact_baselines, monkeypatch
) -> None:
    """The learned detector and immutable E022 pose gate may disagree."""
    height = width = 24
    yy, xx = np.meshgrid(
        np.arange(height), np.arange(width), indexing="ij"
    )
    physical = ((yy + xx) % 2).astype(np.uint8).ravel()
    placed = t23._placed_window(
        np.asarray((120, 120)),
        0,
        0,
        height,
        width,
        origin_px=(3.5, 3.5),
    )
    labels = replace(
        _spatial_labels(physical, placed.page_cells_yx),
        is_pilot=(np.arange(physical.size) % 4 == 0),
    )
    assert int((labels.train & labels.is_pilot).sum()) >= 20
    assert int((labels.validation & labels.is_pilot).sum()) >= 20

    mid = 100.0
    spread = 20.0
    base_means = np.where(
        physical > 0, mid - 1.1 * spread, mid + 0.1 * spread
    ).astype(np.float32)
    pass_means = np.where(
        physical > 0, mid - 2.0 * spread, mid + 0.1 * spread
    ).astype(np.float32)
    # Zero-valued cells are below the raw midpoint, but their detector score
    # remains below the deliberately shifted zero-logit threshold at 1.0.
    fail_means = np.where(
        physical > 0, mid - 2.0 * spread, mid - 0.5 * spread
    ).astype(np.float32)
    generation0 = payloaddec.WindowEmission(
        placement_ordinal=0,
        page=0,
        payload_index=np.zeros(0, np.int64),
        payload_llr=np.zeros(0, np.float32),
        heldout_logloss=float(np.log(2.0)),
        n_train_labels=int(labels.train.sum()),
        n_heldout=int(labels.validation.sum()),
        region_index=0,
        page_cells_yx=np.asarray(
            placed.page_cells_yx, np.int32
        ).copy(),
        raw_means=base_means,
        scores=((mid - base_means) / spread).astype(np.float32),
        calibration_score_nodes=np.array([0.0, 2.0], np.float64),
        calibration_probability_nodes=np.array([0.25, 0.75], np.float64),
        diagnostics={"mid": mid, "spread": spread},
    )
    crop = payloaddec.RegionCrop(
        y0=0,
        x0=0,
        filt=np.zeros((2, 2), np.float32),
        fill=mid,
    )
    config = FeedbackConfig(
        block_cells=4,
        min_payload_train=64,
        min_payload_validation=32,
        min_label_blocks=4,
        min_improvement=1e-4,
        pose_angle_deg=0.0,
        pose_phase_cells=0.125,
        pose_phase_coarse_step_cells=0.125,
        pose_phase_fine_step_cells=0.0625,
        pilot_mismatch_slack=0.0,
    )
    candidate = {"means": pass_means}

    def row_positions(local_cells):
        cells = np.rint(np.asarray(local_cells)).astype(np.int64)
        return cells[:, 0] * width + cells[:, 1]

    def sample_window_means(_crop, candidate_placed, local_cells):
        source = (
            base_means
            if candidate_placed.pose == placed.pose
            else candidate["means"]
        )
        return source[row_positions(local_cells)]

    def sample_pose_sites(_crop, pose, local_cells):
        source = (
            base_means if pose == placed.pose else candidate["means"]
        )
        return source[row_positions(local_cells)]

    with monkeypatch.context() as runtime_patch:
        runtime_patch.setattr(
            payloaddec, "sample_window_means", sample_window_means
        )
        runtime_patch.setattr(
            feedback, "_sample_pose_sites", sample_pose_sites
        )
        pose, revised_means, pass_metrics = (
            feedback.refine_pose_on_labels(
                crop, placed, generation0, labels, config
            )
        )
        assert pose is not None and revised_means is not None
        assert pass_metrics["adopted"]
        assert pass_metrics["candidate_pilot_mismatch"] == 0.0
        assert pass_metrics["candidate_e022_pilot_mismatch"] == 0.0

        candidate["means"] = fail_means
        pose, revised_means, fail_metrics = (
            feedback.refine_pose_on_labels(
                crop, placed, generation0, labels, config
            )
        )
        assert pose is None and revised_means is None
        assert not fail_metrics["adopted"]
        assert fail_metrics["reason"] == "pose_gate_failed"
        assert fail_metrics["candidate_validation_logloss"] < (
            fail_metrics["baseline_validation_logloss"]
        )
        assert fail_metrics["candidate_pilot_mismatch"] == 0.0
        assert fail_metrics["generation0_e022_pilot_mismatch"] == 0.0
        assert fail_metrics["candidate_e022_pilot_mismatch"] > 0.0

    baseline, session, revision = _accepted_revision_overlay(
        compact_baselines, monkeypatch, profile=PROFILE_COMBINED
    )
    scan = baseline.scans[0]
    placement = scan.result.placements[revision.placement_ordinal]
    if revision.pose == placement.pose:
        session = copy.deepcopy(session)
        revision = _rekey_revision(
            session, revision.revision_id,
            pose=feedback._pose_candidate(
                placement.pose, 0.0, 0.0625, -0.0625))
    original = scan.window_evidence[revision.placement_ordinal]
    site_pos, expected, validation = payloaddec._window_pilot_observations(
        placement, baseline.decode.spec, baseline.decode.seed
    )
    pilot_rows = site_pos[validation]
    pilot_expected = expected[validation]
    assert int(validation.sum()) >= baseline.envelope.search_config.min_support
    assert np.any(pilot_expected == 0)
    assert np.any(pilot_expected == 1)
    original_mid = float(original.diagnostics.get(
        "mid", np.median(original.raw_means)
    ))
    original_mismatch = float(np.mean(
        (np.asarray(original.raw_means)[pilot_rows] < original_mid)
        != (pilot_expected > 0)
    ))

    def state_gate_emission(*, raw_zero_is_wrong):
        gate_spread = 40.0
        raw_means = np.asarray(
            revision.emission.raw_means, np.float32
        ).copy()
        raw_means[pilot_rows] = np.where(
            pilot_expected > 0,
            original_mid - 2.0 * gate_spread,
            (
                original_mid - 0.5 * gate_spread
                if raw_zero_is_wrong
                else original_mid + 0.1 * gate_spread
            ),
        ).astype(np.float32)
        scores = (
            (original_mid - raw_means.astype(np.float64)) / gate_spread
        ).astype(np.float32)
        diagnostics = {
            "detector_profile": feedback.DETECTOR_PROFILE,
            "feedback_base_clip": 8.0,
            "feedback_context_tau": tuple(np.zeros(9)),
            "feedback_context_clip": 8.0,
            "feedback_context_adopted": False,
            "mid": original_mid,
            "spread": gate_spread,
        }
        page_yx = np.asarray(
            revision.emission.page_cells_yx, np.int64
        )
        payload_map = compose.payload_index_map(
            baseline.decode.spec, baseline.decode.seed
        )
        payload_index = payload_map[
            page_yx[:, 0], page_yx[:, 1]
        ]
        selected = payload_index >= 0
        emission = replace(
            revision.emission,
            payload_index=payload_index[selected].astype(np.int64),
            payload_llr=np.zeros(int(selected.sum()), np.float32),
            heldout_logloss=0.0,
            diagnostics=diagnostics,
            raw_means=raw_means,
            scores=scores,
            calibration_score_nodes=np.array(
                [0.0, 2.0], np.float64
            ),
            calibration_probability_nodes=np.array(
                [0.25, 0.75], np.float64
            ),
            detector_profile=feedback.DETECTOR_PROFILE,
            context_fit=None,
        )
        physical_logits = feedback._physical_logits(emission)
        assert physical_logits is not None
        assert np.all(
            (physical_logits[pilot_rows] > 0.0)
            == (pilot_expected > 0)
        )
        keystream = compose.payload_keystream(
            baseline.decode.spec, baseline.decode.seed, emission.page
        )
        payload_llr = (
            physical_logits[selected]
            * (
                1.0
                - 2.0
                * keystream[
                    page_yx[selected, 0], page_yx[selected, 1]
                ].astype(np.float64)
            )
        ).astype(np.float32)
        emission = replace(emission, payload_llr=payload_llr)
        return feedback._set_comparable_owner_rank(
            emission, replace(placement, pose=revision.pose), baseline
        )

    passing_emission = state_gate_emission(raw_zero_is_wrong=False)
    passing_mismatch = float(np.mean(
        (passing_emission.raw_means[pilot_rows] < original_mid)
        != (pilot_expected > 0)
    ))
    assert passing_mismatch == 0.0
    passing = copy.deepcopy(session)
    _rekey_revision(
        passing, revision.revision_id, emission=passing_emission
    )
    feedbackstate.validate_session(
        passing,
        baseline,
        check_baseline_artifact=False,
        validate_baseline=False,
        replay_projections=False,
        replay_decisions=False,
    )

    failing_emission = state_gate_emission(raw_zero_is_wrong=True)
    failing_mismatch = float(np.mean(
        (failing_emission.raw_means[pilot_rows] < original_mid)
        != (pilot_expected > 0)
    ))
    assert failing_mismatch > original_mismatch
    failing = copy.deepcopy(session)
    _rekey_revision(
        failing, revision.revision_id, emission=failing_emission
    )
    with pytest.raises(
        ValueError, match="violates the E022 pilot gate"
    ):
        feedbackstate.validate_session(
            failing,
            baseline,
            check_baseline_artifact=False,
            validate_baseline=False,
            replay_projections=False,
            replay_decisions=False,
        )


def _revision(
    session: feedbackstate.E024Session,
    baseline: receiver.ReceiverSession,
    *,
    generation: int,
    parent_revision_id: str | None,
    dependency_ids,
    llr_scale: float,
) -> EvidenceRevision:
    scan = baseline.scans[0]
    parent = (
        scan.window_evidence[0]
        if parent_revision_id is None
        else session.revisions[parent_revision_id].emission
    )
    assert parent is not None
    emission = copy.deepcopy(parent)
    emission.payload_llr = (
        np.asarray(emission.payload_llr, np.float32)
        * np.float32(llr_scale)
    )
    dependency_set_id = feedbackstate.intern_dependency_set(
        session, dependency_ids
    )
    metrics = {"fixture": "target-specific-supersession"}
    revision_id = feedbackstate.revision_identity(
        scan_id=scan.scan_id,
        placement_id=scan.placement_ids[0],
        generation=generation,
        arm=PROFILE_RECAL,
        parent_revision_id=parent_revision_id,
        dependency_set_id=dependency_set_id,
        label_uses=(),
        pose=scan.result.placements[0].pose,
        emission=emission,
        accepted=True,
        refuse_reason="",
        metrics=metrics,
    )
    return EvidenceRevision(
        revision_id=revision_id,
        scan_id=scan.scan_id,
        capture_id=scan.capture_id,
        placement_ordinal=0,
        placement_id=scan.placement_ids[0],
        generation=generation,
        arm=PROFILE_RECAL,
        parent_revision_id=parent_revision_id,
        dependency_set_id=dependency_set_id,
        label_uses=(),
        pose=scan.result.placements[0].pose,
        emission=emission,
        accepted=True,
        refuse_reason="",
        metrics=metrics,
    )


def _accepted_revision_overlay(
    compact_baselines,
    monkeypatch,
    *,
    profile=PROFILE_COMBINED,
    mock_decode=True,
):
    """Commit one replay-valid revision, dependency and physical patch."""
    baseline = compact_baselines["demoted"]
    session = feedback.create_session(
        compact_baselines["demoted_path"],
        baseline,
        profile=profile,
    )

    def accepted_revision(
        working,
        substrate,
        label_field,
        targets,
        _labels_by_window,
        generation,
    ):
        scan = substrate.scans[0]
        placed = scan.result.placements[0]
        parent = scan.window_evidence[0]
        page_yx = np.asarray(placed.page_cells_yx, np.int64)
        labels = feedback.collect_window_labels(
            placed, label_field, substrate, working.envelope.config)
        known = np.zeros(page_yx.shape[0], bool)
        known[labels.row_positions] = True
        physical = np.zeros(page_yx.shape[0], np.uint8)
        physical[labels.row_positions] = labels.values
        unknown = np.flatnonzero(~known)
        target_ones = physical.size // 2
        needed_ones = max(min(
            target_ones - int(physical[known].sum()),
            int(unknown.size)), 0)
        physical[unknown[:needed_ones]] = 1
        raw_means = np.where(
            physical > 0, 0.0, 200.0).astype(np.float32)
        scores64, mid, spread = feedback._scores_from_means(raw_means)
        scores = np.asarray(scores64, np.float32)
        nodes_s = np.array([
            float(scores.min()), -1e-6, 1e-6,
            float(scores.max())], np.float64)
        nodes_p = np.array(
            [1e-4, 1e-4, 1.0 - 1e-4, 1.0 - 1e-4],
            np.float64)
        diagnostics = {
            "detector_profile": feedback.DETECTOR_PROFILE,
            "feedback_base_clip": 8.0,
            "feedback_context_tau": tuple(np.zeros(9)),
            "feedback_context_clip": 8.0,
            "feedback_context_adopted": False,
            "mid": float(mid),
            "spread": float(spread),
        }
        pidx = label_field.payload_index_map[
            page_yx[:, 0], page_yx[:, 1]
        ]
        selected = pidx >= 0
        keystream = label_field.keystream_pages[int(placed.page)]
        emission = replace(
            parent,
            payload_index=pidx[selected].astype(np.int64),
            payload_llr=np.zeros(int(selected.sum()), np.float32),
            heldout_logloss=0.125,
            diagnostics=diagnostics,
            raw_means=raw_means,
            scores=np.asarray(scores, np.float32),
            calibration_score_nodes=nodes_s,
            calibration_probability_nodes=nodes_p,
            detector_profile=feedback.DETECTOR_PROFILE,
            context_fit=None,
        )
        physical_logits = feedback._physical_logits(emission)
        assert physical_logits is not None
        payload_llr = (
            physical_logits[selected]
            * (
                1.0
                - 2.0
                * keystream[
                    page_yx[selected, 0], page_yx[selected, 1]
                ].astype(np.float64)
            )
        ).astype(np.float32)
        emission = replace(emission, payload_llr=payload_llr)
        pose = placed.pose
        emission = feedback._set_comparable_owner_rank(
            emission, replace(placed, pose=pose), substrate
        )
        valid = labels.validation
        parent_logits = feedback._physical_logits(parent)
        candidate_logits = feedback._physical_logits(emission)
        assert parent_logits is not None and candidate_logits is not None
        parent_loss = feedback._weighted_logloss(
            parent_logits[labels.row_positions[valid]],
            labels.values[valid], labels.weights[valid])
        candidate_loss = feedback._weighted_logloss(
            candidate_logits[labels.row_positions[valid]],
            labels.values[valid], labels.weights[valid])
        assert (
            candidate_loss + working.envelope.config.min_improvement
            < parent_loss)
        _parent_scores, parent_fixed = (
            feedback._generation0_detector_logits(
                parent, placed.page_cells_yx, parent.raw_means))
        _candidate_scores, candidate_fixed = (
            feedback._generation0_detector_logits(
                parent, placed.page_cells_yx, emission.raw_means))
        pose_parent_loss = feedback._weighted_logloss(
            parent_fixed[labels.row_positions[valid]],
            labels.values[valid], labels.weights[valid])
        pose_candidate_loss = feedback._weighted_logloss(
            candidate_fixed[labels.row_positions[valid]],
            labels.values[valid], labels.weights[valid])

        certificate = next(iter(working.certificates.values()))
        dependency_set_id = feedbackstate.intern_dependency_set(
            working, [certificate.certificate_id]
        )
        payload_indices = label_field.payload_indices[
            certificate.tile_key
        ]
        label_use = LabelUse(
            certificate_id=certificate.certificate_id,
            role="detector-and-gate",
            n_sites=int(payload_indices.size),
            payload_indices_sha256=feedback._array_digest(
                payload_indices, "<i8"
            ),
        )
        metrics = {
            "fixture": "accepted-report-observer",
            "target_tiles": tuple(
                sorted(tile for rows in targets.values() for tile in rows)
            ),
            "pose": {
                "adopted": False,
                "reason": "baseline_pose_selected",
                "du_cells": 0.0,
                "dv_cells": 0.0,
                "baseline_validation_logloss": pose_parent_loss,
                "candidate_validation_logloss": pose_candidate_loss,
            },
            "detector": {
                "adopted": True,
                "parent_validation_logloss": parent_loss,
                "candidate_validation_logloss": candidate_loss,
            },
        }
        revision_id = feedbackstate.revision_identity(
            scan.scan_id,
            scan.placement_ids[0],
            generation,
            profile,
            None,
            dependency_set_id,
            (label_use,),
            pose,
            emission,
            True,
            "",
            metrics,
        )
        revision = EvidenceRevision(
            revision_id=revision_id,
            scan_id=scan.scan_id,
            capture_id=scan.capture_id,
            placement_ordinal=0,
            placement_id=scan.placement_ids[0],
            generation=generation,
            arm=profile,
            parent_revision_id=None,
            dependency_set_id=dependency_set_id,
            label_uses=(label_use,),
            pose=pose,
            emission=emission,
            accepted=True,
            refuse_reason="",
            metrics=metrics,
        )
        return [revision], [], {
            "candidate_windows": len(targets),
            "accepted": 1,
            "source_tiff_reads": 0,
        }

    monkeypatch.setattr(feedback, "_build_revisions", accepted_revision)
    if mock_decode:
        monkeypatch.setattr(
            feedback,
            "_decode_changed_targets",
            lambda *_args, **_kwargs: (
                [],
                [],
                {
                    "changed_targets": 1,
                    "crc_calls": 0,
                    "new_certificates": 0,
                },
            ),
        )
    advanced, report = feedback.run_feedback_generation(session, baseline)
    assert not report["noop"]
    assert len(advanced.head.accepted_revision_ids) == 1
    assert advanced.head.patch_ids
    revision_id = advanced.head.accepted_revision_ids[0]
    return baseline, advanced, advanced.revisions[revision_id]


def test_single_component_failed_union_dedup_can_parent_retry(
    compact_baselines, monkeypatch,
) -> None:
    real_evaluate = payloaddec.evaluate_tile
    calls = []

    def forced_failure(*args, **kwargs):
        evaluation = real_evaluate(*args, **kwargs)
        assert evaluation.decoder_invoked
        assert evaluation.n_informative >= evaluation.k_eff
        calls.append(int(kwargs["max_iters"]))
        return replace(
            evaluation,
            state="attempted_failed",
            syndrome_ok=False,
            crc_ok=False,
            user_bits=None,
        )

    monkeypatch.setattr(
        payloaddec, "evaluate_tile", forced_failure)
    baseline, session, _revision = _accepted_revision_overlay(
        compact_baselines, monkeypatch,
        profile=PROFILE_RECAL, mock_decode=False)

    assert calls == [60, 150]
    assert [row.stage for row in session.attempts] == [
        "feedback-scan60", "feedback-retry150"]
    scan60, retry150 = session.attempts
    assert (
        scan60.numeric_evidence_sha256
        == retry150.numeric_evidence_sha256)
    assert scan60.component_sha256 == retry150.component_sha256
    assert scan60.dependency_set_id == retry150.dependency_set_id
    feedbackstate.validate_session(
        session, baseline,
        check_baseline_artifact=False,
        validate_baseline=False)


def test_full_validation_rejects_incomplete_candidate_frontier(
    compact_baselines, monkeypatch,
) -> None:
    baseline = compact_baselines["demoted"]
    session = feedback.create_session(
        compact_baselines["demoted_path"],
        baseline,
        profile=PROFILE_RECAL)
    label_field = feedback.export_certified_labels(session, baseline)
    targets, _labels = feedback._candidate_windows(
        session, baseline, label_field)
    assert len(targets) == 1

    real_build = feedback._build_revisions
    monkeypatch.setattr(
        feedback,
        "_build_revisions",
        lambda *_args, **_kwargs: (
            [], [], {
                "candidate_windows": 0,
                "accepted": 0,
                "source_tiff_reads": 0,
            }),
    )
    incomplete, report = feedback.run_feedback_generation(
        session, baseline)
    assert report["reason"] == "no_new_certificates"
    assert incomplete.head.fixed_point
    assert not incomplete.head.accepted_revision_ids
    assert not incomplete.head.refused_revision_ids

    monkeypatch.setattr(feedback, "_build_revisions", real_build)
    with pytest.raises(
        ValueError, match="generation decision replay mismatch"
    ):
        feedbackstate.validate_session(
            incomplete, baseline,
            check_baseline_artifact=False,
            validate_baseline=False)


def _generation_with_identity(row, **changes):
    updated = replace(row, **changes)
    identity = feedbackstate.generation_identity(
        updated.ordinal,
        updated.parent_generation_id,
        updated.label_frontier_sha256,
        updated.active_revisions,
        updated.accepted_revision_ids,
        updated.refused_revision_ids,
        updated.patch_ids,
        updated.attempt_ids,
        updated.new_certificate_ids,
        updated.active_projection_sha256,
        updated.fixed_point,
        updated.statistics,
    )
    return replace(updated, generation_id=identity)


def _rekey_revision(session, revision_id, **changes):
    old = session.revisions.pop(revision_id)
    updated = replace(old, **changes)
    new_id = feedbackstate.revision_identity(
        updated.scan_id,
        updated.placement_id,
        updated.generation,
        updated.arm,
        updated.parent_revision_id,
        updated.dependency_set_id,
        updated.label_uses,
        updated.pose,
        updated.emission,
        updated.accepted,
        updated.refuse_reason,
        updated.metrics,
    )
    updated = replace(updated, revision_id=new_id)
    session.revisions[new_id] = updated

    for index, generation in enumerate(session.generations):
        active = tuple(
            (scan_id, ordinal, new_id if value == revision_id else value)
            for scan_id, ordinal, value
            in generation.active_revisions
        )
        accepted = tuple(
            new_id if value == revision_id else value
            for value in generation.accepted_revision_ids
        )
        refused = tuple(
            new_id if value == revision_id else value
            for value in generation.refused_revision_ids
        )
        parent = (
            None
            if index == 0
            else session.generations[index - 1].generation_id
        )
        session.generations[index] = _generation_with_identity(
            generation,
            parent_generation_id=parent,
            active_revisions=active,
            accepted_revision_ids=accepted,
            refused_revision_ids=refused,
        )
    return updated


def _certificate_union_payload(compact_baselines, rows=None):
    sources = merge_e023b.load_sources([
        merge_e023b.SourceSpec(
            "selected",
            compact_baselines["demoted_path"].resolve()),
        merge_e023b.SourceSpec(
            "independent",
            compact_baselines["full_path"].resolve()),
    ])
    payload = merge_e023b.build_union(sources)
    if rows is not None:
        payload["certificates"] = rows
    return payload


def test_nontrivial_accepted_overlay_round_trips(
    compact_baselines, tmp_path, monkeypatch
) -> None:
    baseline, session, revision = _accepted_revision_overlay(
        compact_baselines, monkeypatch
    )
    assert revision.accepted
    assert session.head.accepted_revision_ids == (
        revision.revision_id,
    )
    assert session.head.patch_ids

    state_path = tmp_path / "accepted-e024.pkl"
    feedbackstate.save_session(
        state_path,
        session,
        baseline,
        baseline_path=compact_baselines["demoted_path"],
    )
    loaded, loaded_baseline = feedbackstate.load_session(state_path)

    assert feedbackstate.authoritative_digest(loaded) == (
        feedbackstate.authoritative_digest(session)
    )
    assert receiver.authoritative_digest(loaded_baseline) == (
        receiver.authoritative_digest(baseline)
    )
    assert loaded.head == session.head
    assert tuple(loaded.revisions) == tuple(session.revisions)
    assert tuple(loaded.patches) == tuple(session.patches)
    loaded_revision = loaded.revisions[revision.revision_id]
    assert loaded_revision.accepted
    assert np.array_equal(
        loaded_revision.emission.payload_llr,
        revision.emission.payload_llr,
    )


def test_split_invocation_matches_continuous_feedback(
    compact_baselines, tmp_path, monkeypatch
) -> None:
    """A persisted non-fixed frontier resumes to the identical state."""
    baseline = compact_baselines["demoted"]
    target = compact_baselines["demoted_key"]
    initial = feedback.create_session(
        compact_baselines["demoted_path"],
        baseline,
        profile=PROFILE_RECAL,
    )
    mask = baseline.decode.shorten_mask(target[1:])
    n_user = ldpc.tile_user_capacity(mask, baseline.decode.ldpc_spec)
    evaluation = payloaddec.TileEvaluation(
        state="certified",
        decoder_invoked=True,
        k_eff=max(
            baseline.decode.ldpc_spec.k_bits - int(mask.sum()), 0
        ),
        n_nonshort=int((~mask).sum()),
        n_informative=int((~mask).sum()),
        coverage=1.0,
        n_iters=1,
        syndrome_ok=True,
        crc_ok=True,
        n_erased=0,
        user_bits=np.zeros(n_user, np.uint8),
    )
    monkeypatch.setattr(
        payloaddec, "evaluate_tile", lambda *_args, **_kwargs: evaluation
    )
    window_key = (baseline.scans[0].scan_id, 0)
    monkeypatch.setattr(
        feedback,
        "_candidate_windows",
        lambda *_args, **_kwargs: ({window_key: {target}}, {}),
    )
    monkeypatch.setattr(
        feedback,
        "_build_revisions",
        lambda *_args, **_kwargs: (
            [],
            [],
            {"candidate_windows": 1, "accepted": 0},
        ),
    )
    monkeypatch.setattr(
        feedback, "_build_patches", lambda *_args, **_kwargs: []
    )

    def one_then_duplicate(
        working,
        _previous,
        substrate,
        *,
        generation,
        targets,
        new_active,
        on_attempt=None,
    ):
        del targets
        evidence = feedback.resolve_target_evidence(
            working, substrate, target, new_active)
        assert evidence is not None and len(evidence.components) == 1
        component = evidence.components[0]
        attempt, certificate, created = feedback._apply_attempt(
            working,
            substrate,
            generation=generation,
            target=target,
            stage="feedback-scan60",
            source=component.scan_id,
            index=component.index,
            llr_values=component.llr,
            numeric_sha256=component.numeric_sha256,
            component_sha256=((
                component.capture_id, component.numeric_sha256),),
            revision_ids=component.revision_ids,
            dependency_ids=component.dependency_ids,
            max_iters=working.envelope.config.baseline_bp_max_iters,
        )
        if created and on_attempt is not None:
            on_attempt(working, attempt)
        certificates = (
            [certificate]
            if created and certificate is not None
            and attempt.certified_new
            else []
        )
        return (
            [attempt] if created else [],
            certificates,
            {
                "changed_targets": 1,
                "crc_calls": int(created and attempt.decoder_invoked),
                "new_certificates": len(certificates),
            },
        )

    monkeypatch.setattr(
        feedback, "_decode_changed_targets", one_then_duplicate
    )

    continuous, continuous_report = feedback.run_feedback(
        initial, baseline, max_generations=2
    )
    assert continuous_report["generations_run"] == 2
    assert continuous.head.ordinal == 2
    assert continuous.head.fixed_point

    first, first_report = feedback.run_feedback(
        initial, baseline, max_generations=1
    )
    assert first_report["generations_run"] == 1
    assert first.head.ordinal == 1
    assert not first.head.fixed_point
    tampered_attempt = copy.deepcopy(first)
    tampered_attempt.attempts[0] = replace(
        tampered_attempt.attempts[0], syndrome_ok=False)
    with pytest.raises(
        ValueError, match="attempt state semantics"):
        feedbackstate.validate_session(
            tampered_attempt, baseline,
            check_baseline_artifact=False,
            validate_baseline=False,
            replay_attempts=False)
    state_path = tmp_path / "split-e024.pkl"
    feedbackstate.save_session(
        state_path,
        first,
        baseline,
        baseline_path=compact_baselines["demoted_path"],
    )
    resumed_frontier, resumed_baseline = feedbackstate.load_session(
        state_path
    )
    resumed, second_report = feedback.run_feedback(
        resumed_frontier, resumed_baseline, max_generations=1
    )

    assert second_report["generations_run"] == 1
    assert resumed.head.ordinal == 2
    assert resumed.head.fixed_point
    assert first_report["reports"] + second_report["reports"] == (
        continuous_report["reports"]
    )
    assert tuple(
        row.generation_id for row in resumed.generations
    ) == tuple(
        row.generation_id for row in continuous.generations
    )
    assert feedbackstate.authoritative_digest(resumed) == (
        feedbackstate.authoritative_digest(continuous)
    )


def test_target_resolver_falls_back_and_supersedes_per_capture(
    compact_baselines,
) -> None:
    baseline = compact_baselines["baseline"]
    session = feedback.create_session(
        compact_baselines["full_path"],
        baseline,
        profile=PROFILE_RECAL,
    )
    target, parent_dependency, probe, *_ = sorted(session.certificates)
    cert = session.certificates

    # r1 is legal for `target` but itself used a different certificate.
    r1 = _revision(
        session,
        baseline,
        generation=1,
        parent_revision_id=None,
        dependency_ids=[cert[parent_dependency].certificate_id],
        llr_scale=0.75,
    )
    session.revisions[r1.revision_id] = r1
    # r2 has expanded dependencies including both the target and r1's
    # label source. It is therefore legal for `probe`, not for either label.
    r2 = _revision(
        session,
        baseline,
        generation=2,
        parent_revision_id=r1.revision_id,
        dependency_ids=[
            cert[target].certificate_id,
            cert[parent_dependency].certificate_id,
        ],
        llr_scale=0.25,
    )
    session.revisions[r2.revision_id] = r2
    scan = baseline.scans[0]
    active_r1 = {(scan.scan_id, 0): r1.revision_id}
    active_r2 = {(scan.scan_id, 0): r2.revision_id}

    target_from_r1 = feedback.resolve_target_evidence(
        session, baseline, target, active_r1
    )
    target_safe = feedback.resolve_target_evidence(
        session, baseline, target, active_r2
    )
    assert target_from_r1 is not None and target_safe is not None
    assert (
        target_safe.union_numeric_sha256
        == target_from_r1.union_numeric_sha256
    )
    assert target_safe.revision_ids == (r1.revision_id,)
    assert cert[target].certificate_id not in target_safe.dependency_ids
    generic_cache = {
        scan.scan_id: feedback._scan_projection_bound(
            session, baseline, scan, active_r2)}
    target_cached = feedback.resolve_target_evidence(
        session, baseline, target, active_r2,
        projection_cache=generic_cache)
    assert target_cached is not None
    assert (
        target_cached.union_numeric_sha256
        == target_safe.union_numeric_sha256)
    assert target_cached.revision_ids == (r1.revision_id,)

    dependency_safe = feedback.resolve_target_evidence(
        session, baseline, parent_dependency, active_r2
    )
    dependency_baseline = feedback.resolve_target_evidence(
        session, baseline, parent_dependency, {}
    )
    assert dependency_safe is not None and dependency_baseline is not None
    assert (
        dependency_safe.union_numeric_sha256
        == dependency_baseline.union_numeric_sha256
    )
    assert dependency_safe.revision_ids == ()

    probe_evidence = feedback.resolve_target_evidence(
        session, baseline, probe, active_r2
    )
    probe_baseline = feedback.resolve_target_evidence(
        session, baseline, probe, {}
    )
    assert probe_evidence is not None and probe_baseline is not None
    assert probe_evidence.revision_ids == (r2.revision_id,)
    assert (
        probe_evidence.union_numeric_sha256
        != probe_baseline.union_numeric_sha256
    )
    # One scan/capture contributes one selected physical value: the active
    # revision replaces its predecessor instead of being added to it.
    assert len(probe_evidence.components) == 1
    assert np.array_equal(
        probe_evidence.union_index, probe_evidence.components[0].index
    )
    assert np.array_equal(
        probe_evidence.union_llr, probe_evidence.components[0].llr
    )

    duplicate_capture = baseline.fork()
    duplicate_capture.scans.append(copy.deepcopy(duplicate_capture.scans[0]))
    with pytest.raises(
        payloaddec.FatalIntegrityError, match="sum one capture twice"
    ):
        feedback.resolve_target_evidence(
            session, duplicate_capture, probe, active_r2
        )


def test_combined_arm_recalibrates_when_pose_stays_at_baseline(
    compact_baselines, monkeypatch
) -> None:
    """Combined means pose-if-better plus recal, not pose-gated recal."""
    baseline = compact_baselines["demoted"]
    session = feedback.create_session(
        compact_baselines["demoted_path"],
        baseline,
        profile=PROFILE_COMBINED,
    )
    label_field = feedback.export_certified_labels(session, baseline)
    targets, labels = feedback._candidate_windows(
        session, baseline, label_field
    )
    assert targets

    monkeypatch.setattr(
        feedback,
        "refine_pose_on_labels",
        lambda *_args, **_kwargs: (
            None,
            None,
            {
                "eligible": True,
                "adopted": False,
                "reason": "baseline_pose_selected",
            },
        ),
    )
    recalibrated = []

    def same_pose_recal(
        placed,
        parent,
        means,
        window_labels,
        labels_field,
        substrate,
        config,
    ):
        del placed, means, substrate, config
        candidate = copy.deepcopy(parent)
        candidate.payload_llr = (
            np.asarray(candidate.payload_llr, np.float32)
            * np.float32(0.875)
        )
        recalibrated.append(candidate)
        return (
            candidate,
            {"eligible": True, "adopted": True, "reason": "adopted"},
            feedback._label_uses(window_labels, labels_field),
        )

    monkeypatch.setattr(
        feedback, "fit_detector_revision", same_pose_recal
    )
    accepted, refused, statistics = feedback._build_revisions(
        session,
        baseline,
        label_field,
        targets,
        labels,
        generation=1,
    )
    assert len(recalibrated) == len(targets)
    assert len(accepted) == len(targets)
    assert not refused
    assert statistics["accepted"] == len(targets)
    assert all(
        row.metrics["pose"]["reason"] == "baseline_pose_selected"
        and row.metrics["detector"]["adopted"]
        for row in accepted
    )


def test_unexpected_candidate_error_aborts_private_transaction(
    compact_baselines, monkeypatch
) -> None:
    baseline = compact_baselines["demoted"]
    session = feedback.create_session(
        compact_baselines["demoted_path"],
        baseline,
        profile=PROFILE_RECAL,
    )
    label_field = feedback.export_certified_labels(session, baseline)
    targets, labels = feedback._candidate_windows(
        session, baseline, label_field)
    assert targets

    def fail_candidate(*_args, **_kwargs):
        raise ValueError("injected detector construction failure")

    monkeypatch.setattr(
        feedback, "fit_detector_revision", fail_candidate)
    with pytest.raises(
        payloaddec.FatalIntegrityError,
        match="candidate construction failed.*injected",
    ):
        feedback._build_revisions(
            session, baseline, label_field, targets, labels,
            generation=1)


def test_attempt_dedup_and_generation_barrier(
    compact_baselines, monkeypatch
) -> None:
    baseline = compact_baselines["demoted"]
    target = compact_baselines["demoted_key"]
    session = feedback.create_session(
        compact_baselines["demoted_path"],
        baseline,
        profile=PROFILE_RECAL,
    )
    initial_frontier = tuple(
        sorted(row.certificate_id for row in session.certificates.values())
    )
    mask = baseline.decode.shorten_mask(target[1:])
    n_user = ldpc.tile_user_capacity(mask, baseline.decode.ldpc_spec)
    user_bits = np.zeros(n_user, np.uint8)
    evaluation = payloaddec.TileEvaluation(
        state="certified",
        decoder_invoked=True,
        k_eff=max(
            baseline.decode.ldpc_spec.k_bits - int(mask.sum()), 0
        ),
        n_nonshort=int((~mask).sum()),
        n_informative=int((~mask).sum()),
        coverage=1.0,
        n_iters=1,
        syndrome_ok=True,
        crc_ok=True,
        n_erased=0,
        user_bits=user_bits,
    )
    monkeypatch.setattr(
        payloaddec, "evaluate_tile", lambda *_args, **_kwargs: evaluation
    )

    exported_frontiers = []
    real_export = feedback.export_certified_labels

    def observe_export(
        state, substrate, *, certificate_ids=None
    ):
        exported_frontiers.append(tuple(certificate_ids or ()))
        return real_export(
            state, substrate, certificate_ids=certificate_ids
        )

    monkeypatch.setattr(feedback, "export_certified_labels", observe_export)
    monkeypatch.setattr(
        feedback,
        "_candidate_windows",
        lambda state, *_args, **_kwargs: (
            ({("s000", 0): {target}}, {})
            if target not in state.certificates else ({}, {})),
    )
    monkeypatch.setattr(
        feedback,
        "_build_revisions",
        lambda *_args, **_kwargs: (
            [],
            [],
            {"candidate_windows": 1, "accepted": 0},
        ),
    )
    monkeypatch.setattr(
        feedback, "_build_patches", lambda *_args, **_kwargs: []
    )

    def one_controlled_attempt(
        working,
        _previous,
        substrate,
        *,
        generation,
        targets,
        new_active,
        on_attempt=None,
    ):
        del targets
        evidence = feedback.resolve_target_evidence(
            working, substrate, target, new_active)
        assert evidence is not None and len(evidence.components) == 1
        component = evidence.components[0]
        attempt, certificate, created = feedback._apply_attempt(
            working,
            substrate,
            generation=generation,
            target=target,
            stage="feedback-scan60",
            source=component.scan_id,
            index=component.index,
            llr_values=component.llr,
            numeric_sha256=component.numeric_sha256,
            component_sha256=((
                component.capture_id, component.numeric_sha256),),
            revision_ids=component.revision_ids,
            dependency_ids=component.dependency_ids,
            max_iters=working.envelope.config.baseline_bp_max_iters,
        )
        if created and on_attempt is not None:
            on_attempt(working, attempt)
        attempts = [attempt] if created else []
        certificates = (
            [certificate]
            if created and certificate is not None
            and attempt.certified_new
            else []
        )
        return attempts, certificates, {
            "changed_targets": 1,
            "crc_calls": int(created and attempt.decoder_invoked),
            "new_certificates": len(certificates),
        }

    monkeypatch.setattr(
        feedback, "_decode_changed_targets", one_controlled_attempt
    )

    advanced, report = feedback.run_feedback_generation(session, baseline)
    assert advanced is not session
    assert not report["noop"] and report["new_certificates"] == 1
    certificate = advanced.certificates[target]
    # The first export is the frozen work frontier. A second export is legal
    # only as a read-only look-ahead for deciding whether another generation
    # is reachable.
    assert exported_frontiers[0] == initial_frontier
    assert certificate.certificate_id not in exported_frontiers[0]
    assert certificate.certificate_id in exported_frontiers[1]
    assert advanced.head.label_frontier_ids == initial_frontier
    assert certificate.certificate_id not in advanced.head.label_frontier_ids
    assert advanced.head.new_certificate_ids == (
        certificate.certificate_id,
    )
    assert target not in session.certificates
    assert len(advanced.attempts) == 1

    same, second = feedback.run_feedback_generation(advanced, baseline)
    assert same is advanced
    assert second["noop"] and second["reason"] == "fixed_point"
    assert len(same.attempts) == 1
    assert len(exported_frontiers) == 2


def test_no_reachable_frontier_commits_one_terminal_generation(
    compact_baselines,
) -> None:
    baseline = compact_baselines["baseline"]
    session = feedback.create_session(
        compact_baselines["full_path"],
        baseline,
        profile=PROFILE_RECAL,
    )
    before = pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL)
    advanced, report = feedback.run_feedback_generation(session, baseline)

    assert advanced is not session
    assert pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL) == before
    assert not report["noop"] and report["terminal_noop"]
    assert report["reason"] == "no_reachable_windows"
    assert report["fixed_point"]
    assert advanced.head.ordinal == session.head.ordinal + 1
    assert advanced.head.fixed_point
    assert advanced.head.active_revisions == session.head.active_revisions
    assert (
        advanced.head.active_projection_sha256
        == session.head.active_projection_sha256
    )
    assert advanced.head.accepted_revision_ids == ()
    assert advanced.head.refused_revision_ids == ()
    assert advanced.head.patch_ids == ()
    assert advanced.head.attempt_ids == ()
    assert advanced.head.new_certificate_ids == ()

    terminal = pickle.dumps(advanced, protocol=pickle.HIGHEST_PROTOCOL)
    same, second = feedback.run_feedback_generation(advanced, baseline)
    assert same is advanced
    assert second["noop"] and second["reason"] == "fixed_point"
    assert pickle.dumps(same, protocol=pickle.HIGHEST_PROTOCOL) == terminal


@pytest.mark.parametrize(
    ("profile", "failure"),
    [
        (PROFILE_REFINE, "content"),
        (PROFILE_COMBINED, "metadata"),
    ],
)
def test_pose_profiles_fail_closed_on_source_replay_corruption(
    compact_baselines, tmp_path, monkeypatch, profile, failure
) -> None:
    baseline = compact_baselines["demoted"].fork()
    original_scan = baseline.scans[0]
    source = tmp_path / "relocated.png"
    source.write_bytes(Path(original_scan.source_path).read_bytes())
    source_sha256, source_size = receiver.file_identity(source)
    baseline.scans[0] = replace(
        original_scan,
        source_path=str(source),
        source_sha256=source_sha256,
        source_size=source_size,
    )
    baseline.validate_invariants()
    baseline_path = tmp_path / "relocated_e023b.pkl"
    receiver.save_session(baseline_path, baseline)
    session = feedback.create_session(
        baseline_path, baseline, profile=profile
    )
    before = pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL)

    if failure == "content":
        source.write_bytes(source.read_bytes() + b"\x00")
        message = "source TIFF changed"
    else:
        real_load = receiver.load_image

        def wrong_metadata(path):
            image = real_load(path)
            return np.asarray(image)[:-1]

        monkeypatch.setattr(receiver, "load_image", wrong_metadata)
        message = "source TIFF metadata changed"

    with pytest.raises(payloaddec.FatalIntegrityError, match=message):
        feedback.run_feedback_generation(session, baseline)
    assert pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL) == before


def test_validator_rejects_recalibration_pose_drift(
    compact_baselines, monkeypatch
) -> None:
    baseline, session, revision = _accepted_revision_overlay(
        compact_baselines, monkeypatch, profile=PROFILE_RECAL
    )
    placement = baseline.scans[0].result.placements[0]
    assert revision.pose == placement.pose

    tampered = copy.deepcopy(session)
    _rekey_revision(
        tampered,
        revision.revision_id,
        pose=feedback._pose_candidate(
            placement.pose, 0.0, 0.0625, 0.0
        ),
    )
    with pytest.raises(
        ValueError, match="recalibration revision changed pose"
    ):
        feedbackstate.validate_session(
            tampered,
            baseline,
            check_baseline_artifact=False,
            validate_baseline=False,
            replay_decisions=False,
        )


def test_validator_rejects_rigid_pose_outside_registered_box(
    compact_baselines, monkeypatch
) -> None:
    baseline, session, revision = _accepted_revision_overlay(
        compact_baselines, monkeypatch, profile=PROFILE_COMBINED
    )
    placement = baseline.scans[0].result.placements[0]
    outside = session.envelope.config.pose_phase_cells + 0.0625
    tampered = copy.deepcopy(session)
    _rekey_revision(
        tampered,
        revision.revision_id,
        pose=feedback._pose_candidate(
            placement.pose, 0.0, outside, 0.0
        ),
    )
    with pytest.raises(
        ValueError, match="pose exceeds the registered rigid box"
    ):
        feedbackstate.validate_session(
            tampered,
            baseline,
            check_baseline_artifact=False,
            validate_baseline=False,
            replay_decisions=False,
        )


def test_validator_rejects_fixed_detector_parameter_substitution(
    compact_baselines, monkeypatch
) -> None:
    baseline, session, revision = _accepted_revision_overlay(
        compact_baselines, monkeypatch, profile=PROFILE_COMBINED
    )
    tampered = copy.deepcopy(session)
    fixed_tag_only = replace(
        revision.emission,
        detector_profile=feedback.FIXED_DETECTOR_PROFILE)
    _rekey_revision(
        tampered, revision.revision_id, emission=fixed_tag_only)
    with pytest.raises(
        ValueError,
        match="score replay mismatch|fixed detector differs from generation zero"
    ):
        feedbackstate.validate_session(
            tampered, baseline,
            check_baseline_artifact=False,
            validate_baseline=False,
            replay_decisions=False)


def test_validator_rejects_generation_after_fixed_point(
    compact_baselines,
) -> None:
    baseline = compact_baselines["baseline"]
    session = feedback.create_session(
        compact_baselines["full_path"],
        baseline,
        profile=PROFILE_RECAL,
    )
    fixed, report = feedback.run_feedback_generation(session, baseline)
    assert report["fixed_point"] and fixed.head.fixed_point

    tampered = copy.deepcopy(fixed)
    head = tampered.head
    statistics = {
        "reason": "tampered-generation-after-fixed-point",
        "revision": {},
        "decode": {},
        "patches": 0,
        "changed_cells": 0,
        "certified_before": len(tampered.certificates),
        "certified_after": len(tampered.certificates),
        "new_certificates": 0,
        "target_windows": 0,
        "target_tiles": 0,
    }
    tampered.generations.append(_generation_with_identity(
        head,
        ordinal=head.ordinal + 1,
        parent_generation_id=head.generation_id,
        accepted_revision_ids=(),
        refused_revision_ids=(),
        patch_ids=(),
        attempt_ids=(),
        new_certificate_ids=(),
        fixed_point=True,
        statistics=statistics,
    ))
    with pytest.raises(
        ValueError, match="follows a persisted fixed point"
    ):
        feedbackstate.validate_session(
            tampered,
            baseline,
            check_baseline_artifact=False,
            validate_baseline=False,
        )


def test_validator_rejects_false_terminal_fixed_point_reason(
    compact_baselines,
) -> None:
    baseline = compact_baselines["baseline"]
    session = feedback.create_session(
        compact_baselines["full_path"],
        baseline,
        profile=PROFILE_RECAL,
    )
    fixed, report = feedback.run_feedback_generation(session, baseline)
    assert report["reason"] == "no_reachable_windows"
    tampered = copy.deepcopy(fixed)
    statistics = dict(tampered.head.statistics)
    statistics["reason"] = "new_feedback_frontier"
    tampered.generations[-1] = _generation_with_identity(
        tampered.head, statistics=statistics)
    with pytest.raises(
        ValueError, match="fixed-point flag/reason mismatch"
    ):
        feedbackstate.validate_session(
            tampered, baseline,
            check_baseline_artifact=False,
            validate_baseline=False)


def test_validator_rejects_mutated_control_generation_zero(
    compact_baselines,
) -> None:
    baseline = compact_baselines["baseline"]
    control = feedback.create_session(
        compact_baselines["full_path"],
        baseline,
        profile=feedbackstate.PROFILE_CONTROL,
    )
    tampered = copy.deepcopy(control)
    tampered.generations[0] = _generation_with_identity(
        tampered.generations[0], fixed_point=False
    )
    with pytest.raises(
        ValueError, match="control profile.*generation-zero no-op"
    ):
        feedbackstate.validate_session(
            tampered,
            baseline,
            check_baseline_artifact=False,
            validate_baseline=False,
        )


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (
            {
                "page": 0,
                "n_user_bits": 8,
                "user_bits_packed_hex": "00",
                "pack_bitorder": "little",
            },
            "row 0 is malformed",
        ),
        (
            {
                "page": 0,
                "tile_yx": [99, 99],
                "n_user_bits": 8,
                "user_bits_packed_hex": "00",
                "pack_bitorder": "little",
            },
            "outside the page",
        ),
    ],
)
def test_certificate_union_bad_rows_fail_as_clean_value_error(
    compact_baselines, tmp_path, row, message
) -> None:
    baseline = compact_baselines["demoted"]
    union_path = tmp_path / (
        "malformed-union.json"
        if "tile_yx" not in row
        else "outside-union.json"
    )
    union_path.write_text(json.dumps(
        _certificate_union_payload(
            compact_baselines, [row]),
        sort_keys=True,
        separators=(",", ":"),
    ))
    with pytest.raises(ValueError, match=message) as raised:
        feedback.create_session(
            compact_baselines["demoted_path"],
            baseline,
            profile=feedbackstate.PROFILE_CONTROL,
            certificate_union=union_path,
        )
    assert type(raised.value) is ValueError


def test_certificate_union_attempt_provenance_is_replayed_from_sources(
    compact_baselines, tmp_path,
) -> None:
    payload = _certificate_union_payload(compact_baselines)
    payload["certificates"][0]["sources"][0]["attempt"][
        "evidence_digest"] = "f" * 64
    union_path = tmp_path / "forged-provenance.json"
    union_path.write_text(json.dumps(
        payload, sort_keys=True, separators=(",", ":")))

    with pytest.raises(
        ValueError, match="differs from a replay"
    ):
        feedback.create_session(
            compact_baselines["demoted_path"],
            compact_baselines["demoted"],
            profile=feedbackstate.PROFILE_CONTROL,
            certificate_union=union_path)


@pytest.mark.parametrize(
    "raw",
    [b"null", b"[]", b'"union"', b"1", b'{"version":null}'],
)
def test_certificate_union_malformed_roots_fail_cleanly(
    tmp_path, raw,
) -> None:
    union_path = tmp_path / "malformed-root.json"
    union_path.write_bytes(raw)
    with pytest.raises(ValueError):
        feedback.validate_certificate_union(union_path)


def test_certificate_union_replay_is_json_type_strict(
    compact_baselines, tmp_path,
) -> None:
    payload = _certificate_union_payload(compact_baselines)
    payload["certificates"][0]["page"] = False
    union_path = tmp_path / "bool-for-int.json"
    union_path.write_text(json.dumps(
        payload, sort_keys=True, separators=(",", ":")))
    with pytest.raises(ValueError, match="differs from a replay"):
        feedback.validate_certificate_union(union_path)


def test_diagnostic_footer_uses_provisional_generation_override(
    compact_baselines, monkeypatch
) -> None:
    baseline = compact_baselines["baseline"]
    session = feedback.create_session(
        compact_baselines["full_path"],
        baseline,
        profile=feedbackstate.PROFILE_CONTROL,
    )
    captured = []

    class FooterDraw:
        def text(self, _position, text, **_kwargs):
            captured.append(text)

    monkeypatch.setattr(run_e024, "_descriptor", lambda _format: object())
    monkeypatch.setattr(
        run_e024.receiver,
        "_combined_pilot_result",
        lambda _baseline: object(),
    )
    monkeypatch.setattr(
        run_e024.receiverdiag,
        "compose_diagnostic",
        lambda *_args, **_kwargs:
        run_e024.Image.new("RGB", (32, 24), (0, 0, 0)),
    )
    monkeypatch.setattr(
        run_e024.ImageDraw, "Draw", lambda _image: FooterDraw()
    )

    pages = run_e024.diagnostic_pngs(
        session,
        baseline,
        display_generation=7,
        phase="feedback-scan60",
        panel_width=64,
    )
    assert pages and all(
        value.startswith(b"\x89PNG\r\n\x1a\n")
        for value in pages.values()
    )
    assert len(captured) == len(pages)
    assert all("generation 7" in text for text in captured)
    assert all("generation 0" not in text for text in captured)


def test_report_dict_is_json_and_exposes_revision_provenance(
    compact_baselines, monkeypatch
) -> None:
    baseline, session, revision = _accepted_revision_overlay(
        compact_baselines, monkeypatch
    )
    report = feedback.report_dict(session, baseline)
    restored = json.loads(json.dumps(report, sort_keys=True))

    generation = restored["generations"][-1]
    assert generation["accepted_revision_ids"] == [
        revision.revision_id
    ]
    assert generation["active_revisions"] == [{
        "scan_id": revision.scan_id,
        "placement_ordinal": revision.placement_ordinal,
        "revision_id": revision.revision_id,
    }]
    assert generation["patch_ids"] == list(session.head.patch_ids)

    row = next(
        value
        for value in restored["revisions"]
        if value["revision_id"] == revision.revision_id
    )
    assert row["accepted"] and row["arm"] == PROFILE_COMBINED
    assert row["scan_id"] == revision.scan_id
    assert row["capture_id"] == revision.capture_id
    assert row["dependency_set_id"] == revision.dependency_set_id
    assert row["pose"]["origin_yx"] == list(revision.pose.origin_yx)
    assert row["pose"]["jacobian_yx"] == [
        list(value) for value in revision.pose.jacobian_yx
    ]
    assert row["metrics"]["fixture"] == "accepted-report-observer"
    assert not row["metrics"]["pose"]["adopted"]
    assert row["metrics"]["pose"]["reason"] == "baseline_pose_selected"
    assert row["label_uses"][0]["certificate_id"] == (
        revision.label_uses[0].certificate_id
    )
    assert row["label_uses"][0]["n_sites"] > 0
    assert row["emission"]["detector_profile"] == (
        feedback.DETECTOR_PROFILE
    )
    assert row["emission"]["owner_rank_logloss"] == pytest.approx(
        revision.emission.heldout_logloss
    )
    assert len(row["emission"]["payload_llr_sha256"]) == 64
    assert len(row["emission"]["raw_means_sha256"]) == 64

    dependency = next(
        value
        for value in restored["dependency_sets"]
        if value["dependency_set_id"] == revision.dependency_set_id
    )
    assert dependency["size"] == 1
    assert dependency["certificate_ids"] == [
        revision.label_uses[0].certificate_id
    ]
    assert dependency["tile_keys"] == [
        list(
            session.certificates[
                next(
                    key
                    for key, certificate in session.certificates.items()
                    if certificate.certificate_id
                    == revision.label_uses[0].certificate_id
                )
            ].tile_key
        )
    ]

    patch = next(
        value
        for value in restored["patches"]
        if value["patch_id"] == session.head.patch_ids[0]
    )
    assert patch["generation"] == revision.generation
    assert patch["scan_id"] == revision.scan_id
    assert patch["capture_id"] == revision.capture_id
    assert patch["changed_cells"] > 0
    assert patch["previous_projection_sha256"] != (
        patch["new_projection_sha256"]
    )
    assert len(patch["payload_indices_sha256"]) == 64
    assert len(patch["previous_owner_sha256"]) == 64
    assert len(patch["new_owner_sha256"]) == 64


def test_provisional_active_map_selects_revision_for_observer_views(
    compact_baselines, monkeypatch
) -> None:
    baseline, session, revision = _accepted_revision_overlay(
        compact_baselines, monkeypatch
    )
    session = copy.deepcopy(session)
    placement = baseline.scans[0].result.placements[0]
    revision = _rekey_revision(
        session, revision.revision_id,
        pose=feedback._pose_candidate(
            placement.pose, 0.0, 0.0625, -0.0625))
    scan = baseline.scans[0]
    provisional_map = {
        (revision.scan_id, revision.placement_ordinal):
        revision.revision_id
    }
    baseline_before = pickle.dumps(
        baseline, protocol=pickle.HIGHEST_PROTOCOL
    )
    session_before = pickle.dumps(
        session, protocol=pickle.HIGHEST_PROTOCOL
    )

    source_view = feedback.materialize_receiver_view(
        session, baseline, active_map={}
    )
    provisional_view = feedback.materialize_receiver_view(
        session, baseline, active_map=provisional_map
    )
    source_vector = source_view.scans[0].emission.pages[0]
    baseline_vector = scan.emission.pages[0]
    for name in ("index", "llr", "owner"):
        assert np.array_equal(source_vector[name], baseline_vector[name])
    assert source_view.decode.scans[0] is (
        source_view.scans[0].emission
    )
    assert source_view.scans[0].source_path == scan.source_path
    assert source_view.scans[0].capture_id == scan.capture_id

    provisional_vector = provisional_view.scans[0].emission.pages[0]
    order = np.argsort(revision.emission.payload_index, kind="stable")
    assert np.array_equal(
        provisional_vector["index"],
        revision.emission.payload_index[order],
    )
    assert np.array_equal(
        provisional_vector["llr"],
        revision.emission.payload_llr[order],
    )
    assert np.all(
        provisional_vector["owner"]
        == revision.placement_ordinal
    )
    assert not np.array_equal(
        provisional_vector["llr"], source_vector["llr"]
    )
    assert provisional_view.decode.scans[0] is (
        provisional_view.scans[0].emission
    )

    source_display = run_e024._display_result(
        session, scan, active_map={}
    )
    provisional_display = run_e024._display_result(
        session, scan, active_map=provisional_map
    )
    assert source_display.placements[0].pose == (
        scan.result.placements[0].pose
    )
    assert provisional_display.placements[0].pose == revision.pose
    assert provisional_display.placements[0].pose != (
        source_display.placements[0].pose
    )

    unresolved = compact_baselines["demoted_key"]
    assert source_view.decode.tiles[unresolved].state == (
        session.tiles[unresolved].state
    )
    assert provisional_view.decode.tiles[unresolved].state == (
        session.tiles[unresolved].state
    )
    assert (
        pickle.dumps(baseline, protocol=pickle.HIGHEST_PROTOCOL)
        == baseline_before
    )
    assert (
        pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL)
        == session_before
    )


def test_materialized_diagnostic_view_is_observer_only(
    compact_baselines,
) -> None:
    baseline = compact_baselines["baseline"]
    session = feedback.create_session(
        compact_baselines["full_path"],
        baseline,
        profile=PROFILE_RECAL,
    )
    baseline_before = pickle.dumps(
        baseline, protocol=pickle.HIGHEST_PROTOCOL
    )
    session_before = pickle.dumps(
        session, protocol=pickle.HIGHEST_PROTOCOL
    )
    baseline_digest = receiver.authoritative_digest(baseline)
    session_digest = feedbackstate.authoritative_digest(session)

    view = feedback.materialize_receiver_view(session, baseline)
    assert view is not baseline
    assert receiver.authoritative_digest(baseline) == baseline_digest
    assert feedbackstate.authoritative_digest(session) == session_digest
    assert (
        pickle.dumps(baseline, protocol=pickle.HIGHEST_PROTOCOL)
        == baseline_before
    )
    assert (
        pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL)
        == session_before
    )

    vector = view.scans[0].emission.pages[0]
    vector["llr"][0] += np.float32(100.0)
    key = next(iter(session.certificates))
    view.decode.tiles[key].user_bits[0] ^= np.uint8(1)
    assert (
        pickle.dumps(baseline, protocol=pickle.HIGHEST_PROTOCOL)
        == baseline_before
    )
    assert (
        pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL)
        == session_before
    )

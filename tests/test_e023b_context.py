"""Focused pins for E023b's registered one-shot ctx + PAVA arm."""
from __future__ import annotations

import pickle
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import compose, payloaddec, pilotsearch  # noqa: E402
import test_e023 as t23  # noqa: E402


def test_context_neighbor_counts_require_all_eight_same_core_neighbors(
) -> None:
    yy, xx = np.meshgrid(np.arange(20, 24), np.arange(30, 34),
                         indexing="ij")
    page_yx = np.stack((yy, xx), axis=-1).reshape(-1, 2)
    ink = ((page_yx[:, 0] + 2 * page_yx[:, 1]) % 3 == 0)
    count, valid = payloaddec.context_neighbor_counts(page_yx, ink)

    valid_grid = valid.reshape(4, 4)
    assert np.array_equal(valid_grid, np.array([
        [False, False, False, False],
        [False, True, True, False],
        [False, True, True, False],
        [False, False, False, False],
    ]))
    lookup = {tuple(cell): bool(bit) for cell, bit in zip(page_yx, ink)}
    for pos in np.flatnonzero(valid):
        y, x = page_yx[pos]
        want = sum(lookup[(y + dy, x + dx)]
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                   if (dy, dx) != (0, 0))
        assert count[pos] == want

    # Removing one coordinate invalidates every cell that needs it, even
    # though a neighboring window in the same region could observe it.
    removed = np.all(page_yx == (21, 31), axis=1)
    _, valid_hole = payloaddec.context_neighbor_counts(
        page_yx[~removed], ink[~removed])
    remaining = page_yx[~removed]
    assert not valid_hole[np.all(remaining == (22, 32), axis=1)][0]


def test_ordered_context_fit_is_deterministic_bounded_and_shrunk() -> None:
    # Empty data leaves every fixed symmetric-prior bin exactly at zero.
    empty = payloaddec.fit_ordered_context_offsets(
        np.zeros(0), np.zeros(0, np.int8), np.zeros(0, np.uint8))
    assert np.array_equal(empty, np.zeros(9))

    count = np.repeat(np.arange(9), 24)
    logits = np.zeros(count.size)
    # Decreasing prevalence is already in the registered physical order.
    n_ones = np.array([22, 20, 18, 15, 12, 9, 6, 4, 2])
    labels = np.concatenate([
        np.r_[np.ones(n, np.uint8), np.zeros(24 - n, np.uint8)]
        for n in n_ones
    ])
    a = payloaddec.fit_ordered_context_offsets(logits, count, labels)
    b = payloaddec.fit_ordered_context_offsets(logits, count, labels)
    assert np.array_equal(a, b)
    assert np.all(a[:-1] >= a[1:])
    assert np.all(a >= payloaddec.CTX_OFFSET_MIN)
    assert np.all(a <= payloaddec.CTX_OFFSET_MAX)
    assert a[0] > 0.0 > a[-1]

    # Reversed first two empirical optima violate tau[0] >= tau[1], so the
    # generalized PAVA block pools them to exactly one optimum.
    merged = payloaddec.fit_ordered_context_offsets(
        np.zeros(20), np.repeat([0, 1], 10),
        np.r_[np.zeros(10, np.uint8), np.ones(10, np.uint8)])
    assert merged[0] == merged[1]
    assert np.all(merged[:-1] >= merged[1:])


def _small_scan_fixture(span: int = 50):
    descriptor = t23._descriptor(b"paper-store/e023b-context-small")
    spec = descriptor.spec()
    payload = np.zeros(compose.payload_capacity(spec), np.uint8)
    values = compose.compose_page(
        payload, spec, descriptor.seed, page=0).cell_values
    rng = np.random.default_rng(2320)
    image = t23._render_cells(values[:span, :span], rng, noise=0.5)
    placed = t23._placed_window(
        np.asarray(values.shape), 0, 0, span, span,
        origin_px=(t23.PITCH / 2 - 0.5, t23.PITCH / 2 - 0.5))
    scan = payloaddec.E022Scan(
        scan_id="s000", source_path="synthetic", source_sha256="0" * 64,
        dpi=1600.0,
        result=pilotsearch.SearchResult(placements=[placed]))
    return descriptor, scan, placed, image


def test_pava_profile_is_baseline_byte_identical_and_failed_gate_is_exact(
) -> None:
    descriptor, scan, placed, image = _small_scan_fixture()
    args = (scan, image, descriptor.spec(), descriptor.seed, (0,))
    implicit = payloaddec.collect_window_evidence(*args)
    explicit = payloaddec.collect_window_evidence(
        *args, detector_profile=payloaddec.DETECTOR_PAVA_V1)
    assert pickle.dumps(implicit) == pickle.dumps(explicit)
    replayed = payloaddec.reprofile_window_evidence(
        [placed], implicit, descriptor.spec(), descriptor.seed,
        payloaddec.DETECTOR_PAVA_V1)
    assert replayed.emissions[0] is implicit[0]

    bad_llr = implicit[0].payload_llr.copy()
    bad_llr[0] = np.nextafter(bad_llr[0], np.float32(np.inf))
    with pytest.raises(ValueError, match="payload_llr"):
        payloaddec.reprofile_window_evidence(
            [placed], [replace(implicit[0], payload_llr=bad_llr)],
            descriptor.spec(), descriptor.seed,
            payloaddec.DETECTOR_PAVA_V1)
    bad_nodes = implicit[0].calibration_score_nodes.copy()
    bad_nodes[0] = np.nextafter(bad_nodes[0], np.inf)
    with pytest.raises(ValueError, match="calibration_score_nodes"):
        payloaddec.reprofile_window_evidence(
            [placed], [replace(
                implicit[0], calibration_score_nodes=bad_nodes)],
            descriptor.spec(), descriptor.seed,
            payloaddec.DETECTOR_PAVA_V1)

    # A 50x50 core clears per-window PAVA but cannot provide the registered
    # 80 complete-neighborhood SEARCH pilots.  The context gate must return
    # the exact baseline object, with the decision carried only in its sidecar.
    assert not implicit[0].refused
    result = payloaddec.apply_context_region(
        [placed], implicit, descriptor.spec(), descriptor.seed)
    assert not result.fit.eligible
    assert not result.fit.adopted
    assert result.emissions[0] is implicit[0]
    assert pickle.dumps(result.emissions) == pickle.dumps(tuple(implicit))


def _context_adoption_fixture():
    descriptor = t23._descriptor(b"paper-store/e023b-context-adopt")
    spec = descriptor.spec()
    payload = np.zeros(compose.payload_capacity(spec), np.uint8)
    values = compose.compose_page(
        payload, spec, descriptor.seed, page=0).cell_values
    span = 120
    placed = t23._placed_window(
        np.asarray(values.shape), 0, 0, span, span,
        origin_px=(t23.PITCH / 2 - 0.5, t23.PITCH / 2 - 0.5))
    page_yx = np.asarray(placed.page_cells_yx, np.int64)
    printed = values[page_yx[:, 0], page_yx[:, 1]].astype(bool)
    count, valid = payloaddec.context_neighbor_counts(page_yx, printed)

    # The provisional decisions are exact, but the marginal detector has a
    # deliberately omitted decreasing context offset.  ctx-pava-v1 can learn
    # that offset using pilots alone and should pass its disjoint gate.
    true_tau = np.linspace(1.5, -1.5, 9)
    l0 = np.where(printed, 2.0, -2.0)
    l0[valid] -= true_tau[count[valid]]

    pim = compose.payload_index_map(spec, descriptor.seed)
    ks_pages = {0: compose.payload_keystream(spec, descriptor.seed, 0)}
    emission = payloaddec._emit_window_from_means(
        placed, 0, (-l0).astype(np.float32), spec, descriptor.seed,
        pim, ks_pages)
    assert not emission.refused
    return descriptor, placed, emission


def test_context_adoption_replays_raw_pava_and_updates_only_derived_evidence(
) -> None:
    descriptor, placed, baseline = _context_adoption_fixture()
    result = payloaddec.apply_context_region(
        [placed], [baseline], descriptor.spec(), descriptor.seed)
    assert result.fit.eligible and result.fit.adopted
    assert result.fit.candidate_validation_logloss < (
        result.fit.baseline_validation_logloss)
    assert np.all(result.fit.tau[:-1] >= result.fit.tau[1:])
    assert result.fit.n_search >= payloaddec.CTX_MIN_SEARCH
    assert result.fit.n_validation >= payloaddec.CTX_MIN_VALIDATION
    assert (result.fit.search_observations_by_bin.sum()
            == result.fit.n_search_observations)
    assert (result.fit.validation_observations_by_bin.sum()
            == result.fit.n_validation_observations)
    assert np.all(result.fit.search_support_by_bin
                  <= result.fit.search_observations_by_bin)
    assert np.all(result.fit.validation_support_by_bin
                  <= result.fit.validation_observations_by_bin)

    corrected = result.emissions[0]
    assert corrected is not baseline
    assert corrected.detector_profile == payloaddec.DETECTOR_CTX_PAVA_V1
    assert corrected.context_fit is result.fit
    assert np.array_equal(corrected.scores, baseline.scores)
    assert np.array_equal(corrected.calibration_score_nodes,
                          baseline.calibration_score_nodes)
    assert np.array_equal(corrected.calibration_probability_nodes,
                          baseline.calibration_probability_nodes)
    assert not np.array_equal(corrected.payload_llr, baseline.payload_llr)
    assert corrected.heldout_logloss < baseline.heldout_logloss

    duplicate = payloaddec.apply_context_region(
        [placed, placed], [baseline, baseline],
        descriptor.spec(), descriptor.seed)
    assert duplicate.fit.n_search == result.fit.n_search
    assert duplicate.fit.n_validation == result.fit.n_validation
    assert duplicate.fit.n_search_observations == 2 * (
        result.fit.n_search_observations)
    assert duplicate.fit.n_validation_observations == 2 * (
        result.fit.n_validation_observations)
    assert np.array_equal(
        duplicate.fit.search_observations_by_bin,
        2 * result.fit.search_observations_by_bin)
    assert np.array_equal(
        duplicate.fit.validation_observations_by_bin,
        2 * result.fit.validation_observations_by_bin)
    assert np.allclose(duplicate.fit.tau, result.fit.tau, atol=1e-11,
                       rtol=0.0)
    assert np.isclose(duplicate.fit.baseline_validation_logloss,
                      result.fit.baseline_validation_logloss)
    assert np.isclose(duplicate.fit.candidate_validation_logloss,
                      result.fit.candidate_validation_logloss)

    # Detector reprofiling uses no pixels: it reconstructs the baseline row
    # exactly and deterministically reapplies the context arm by region.
    replay_base = payloaddec.reprofile_window_evidence(
        [placed], [corrected], descriptor.spec(), descriptor.seed,
        payloaddec.DETECTOR_PAVA_V1)
    assert pickle.dumps(replay_base.emissions[0]) == pickle.dumps(baseline)
    replay_ctx = payloaddec.reprofile_window_evidence(
        [placed], [corrected], descriptor.spec(), descriptor.seed,
        payloaddec.DETECTOR_CTX_PAVA_V1)
    assert len(replay_ctx.context_fits) == 1
    assert np.array_equal(replay_ctx.context_fits[0].tau, result.fit.tau)
    assert np.array_equal(replay_ctx.emissions[0].payload_llr,
                          corrected.payload_llr)


def test_reprofile_legacy_missing_profile_attrs_preserves_pava_object() -> None:
    descriptor, placed, baseline = _context_adoption_fixture()
    # Mimic an E023b.0 object restored from a pickle written before these two
    # dataclass fields existed.
    del baseline.__dict__["detector_profile"]
    del baseline.__dict__["context_fit"]
    replay_base = payloaddec.reprofile_window_evidence(
        [placed], [baseline], descriptor.spec(), descriptor.seed,
        payloaddec.DETECTOR_PAVA_V1)
    assert replay_base.emissions[0] is baseline
    assert "detector_profile" not in baseline.__dict__
    assert "context_fit" not in baseline.__dict__

    replay_ctx = payloaddec.reprofile_window_evidence(
        [placed], [baseline], descriptor.spec(), descriptor.seed,
        payloaddec.DETECTOR_CTX_PAVA_V1)
    assert replay_ctx.emissions[0] is not baseline
    assert hasattr(replay_ctx.emissions[0], "detector_profile")
    assert hasattr(replay_ctx.emissions[0], "context_fit")

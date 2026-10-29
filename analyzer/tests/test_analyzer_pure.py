"""W8 B6 — `analyzer.pure`: the pure path, detector straight to decoder.

Synthetic throughout.  `_state_world` builds a footprint whose score is
exactly ±1 with a known number of deliberate flips, so the held-out error
rate and therefore the LLR magnitude are arithmetic, not approximate;
`_patch_world.World` supplies real (synthetic) pixels and the real
B1 filter for the end-to-end legs.

The pins that matter are the blind ones: the halo's error rate is
measured only on fit-fold labels the threshold never saw, both cross-fit
directions are published, shuffled labels collapse the price to chance
(the cap, a fifth of a bit) instead of to confident nonsense, and the
select-fold label arrays are the ones `select_arm` already pairs on — so
the two calibration paths are compared on the number the decoder
actually consumes.

W8 F2 (the user's rulings on the first trial, APPROACHES §6.5): a cell
whose sibling state is unknown is an ERASURE (LLR 0, counted); a known
state is priced by the TILE — the equal-prior two-component fit on its
own cargo scores — with the halo's held-out error as a FLOOR.  The pins:
a well-separated tile prices at the floor, an overlapping tile prices
its own overlap and not the halo's, a permuted filter prices itself near
chance on its own tile, the fit is deterministic, and nothing — no map,
no context, no Platt, no refit — stands between the discriminant and BP.
"""

from __future__ import annotations

import ast
import math
import pathlib
from dataclasses import replace as dc_replace

import numpy as np
import pytest

from analyzer import arms as arms_mod
from analyzer import calibrate as cal
from analyzer import fixedpoint as fp
from analyzer import frame as frame_mod
from analyzer import patch as patch_mod
from analyzer import pure
from analyzer import statecal
from analyzer.types import (PROFILES, AnalyzerConfig, Evidence, KnownFrame,
                            LaneFootprint, TileFootprint, with_profile)

from ._synthetic import R0850, row_of
from .test_analyzer_gaps_fix import _FakeInputs
from ._patch_world import HALO, World
from .test_analyzer_progress import _FakeRun, _stubbed_driver

SEED = 20260906
#: log((1 - e) / e) at the two ends of the clamp — the whole price range.
FLOOR_WEIGHT = float(np.log((1.0 - pure.ERROR_FLOOR) / pure.ERROR_FLOOR))
CEILING_WEIGHT = float(np.log((1.0 - pure.ERROR_CEILING)
                              / pure.ERROR_CEILING))


# --------------------------------------------------------- the fixtures

def _state_world(n: int = 2400, *, state: int | None = 3, seed: int = 3,
                 known_fraction: float = 0.5, plane: int = 0,
                 word_every: int = 0):
    """A footprint of `n` cells, all in ONE sibling state, half labelled.

    Every sibling bit is proven, so `sibling_state` is `state` for every
    cell; `known[:, plane]` is True on `known_fraction` of the rows (the
    labels a run would have from certified neighbours), and the target
    bits are balanced.  `word_every`-th labelled cell is a word site.
    `state=None` lets the sibling bits vary, which is what the
    discriminating-label floor `select_arm` gates on needs (inside ONE
    state that flag is degenerate — `statecal`'s module docstring).
    """
    rng = np.random.default_rng(seed)
    side = int(np.ceil(np.sqrt(n)))
    cells = np.stack(np.meshgrid(np.arange(side), np.arange(side),
                                 indexing="ij"), axis=-1).reshape(-1, 2)[:n]
    left, right = statecal.spectral.siblings_of(plane)
    bits = np.zeros((n, 3), np.uint8)
    bits[:, plane] = rng.integers(0, 2, n, dtype=np.uint8)
    if state is None:
        bits[:, left] = rng.integers(0, 2, n, dtype=np.uint8)
        bits[:, right] = rng.integers(0, 2, n, dtype=np.uint8)
    else:
        bits[:, left] = np.uint8(state & 1)
        bits[:, right] = np.uint8((state >> 1) & 1)
    known = np.ones((n, 3), bool)
    known[:, plane] = rng.random(n) < known_fraction
    kind = np.full(n, -1, np.int8)
    if word_every:
        rows = np.flatnonzero(known[:, plane])[::word_every]
        kind[rows] = statecal.FURNITURE_WORD
    fp_ = TileFootprint(page=0, ty=0, tx=0, halo_cells=0,
                        page_cells_yx=cells, in_tile=np.ones(n, bool),
                        cargo=np.ones(n, bool),
                        page_shape_cells_yx=(side, side))
    frame = KnownFrame(
        bits=bits, known=known, furniture=kind >= 0, metadata_cell=None,
        regressors=known.all(axis=1), labels=known[:, plane].copy(),
        siblings=known[:, left] & known[:, right], n_discriminating=0,
        furniture_kind=kind, target=(0, 0, 0, "CMY"[plane]), detail={})
    lfp = LaneFootprint(lane=("cap", 0), tile=fp_,
                        observed=np.ones(n, bool),
                        owner_index=np.zeros(n, np.int32),
                        points_yx=np.zeros((n, 2)))
    return frame, lfp, cells, cal.split_folds(cells, SEED)


def _halves(cells: np.ndarray, folds) -> np.ndarray:
    """The cross-fit split `pure` uses — `patch`'s, by construction."""
    return cal.fold_hash(cells, int(folds.seed)
                         ^ patch_mod.CROSSFIT_SALT) < 0.5


def _flipped_score(frame, folds, cells, plane: int = 0,
                   fraction: int = 10) -> tuple[np.ndarray, np.ndarray]:
    """±1 on the target bit, with every `fraction`-th labelled fit row of
    each (half, class) group put on the WRONG side.  The hard decision is
    `sign(score)` for any |threshold| < 1, so the held-out error count is
    exactly the number of flipped rows in the evaluated half."""
    bits = np.asarray(frame.bits[:, plane], np.uint8)
    score = np.where(bits == 1, 1.0, -1.0)
    half = _halves(cells, folds)
    train = np.asarray(frame.known[:, plane], bool) & folds.fit
    flip = np.zeros(bits.size, bool)
    for side in (True, False):
        for value in (0, 1):
            rows = np.flatnonzero(train & (half == side) & (bits == value))
            flip[rows[::fraction]] = True
    score[flip] *= -1.0
    return score, flip


# ------------------------------------------------- the price of a score

def test_the_llr_magnitude_is_the_log_odds_of_the_measured_error_rate():
    """`llr = sign(score - threshold) * log((1 - e) / e)`, and `e` is the
    error of a threshold fitted on the OTHER cross-fit half — counted
    here by hand, row for row."""
    frame, lfp, cells, folds = _state_world()
    score, flip = _flipped_score(frame, folds, cells)
    llr, detail = pure.pure_llr(score, frame, 0, lfp, folds)

    half = _halves(cells, folds)
    train = np.asarray(frame.known[:, 0], bool) & folds.fit
    counts = {}
    for name, side in (("a", True), ("b", False)):
        rows = np.flatnonzero(train & (half == side))
        counts[name] = (int(np.count_nonzero(flip[rows])), int(rows.size))
    wrong = counts["a"][0] + counts["b"][0]
    seen = counts["a"][1] + counts["b"][1]
    expected = wrong / seen
    assert 0.05 < expected < 0.15                 # ~1 in 10, by construction

    entry = detail["pure_populations"]["s3"]
    assert detail["pure_error_by_state"]["s3"] == pytest.approx(expected)
    assert entry["error_raw"] == pytest.approx(expected)
    assert entry["reason"] == "measured" and entry["priced_by"] == "s3"
    # both directions, reported (the build spec's "report both")
    assert entry["error_halves"][0] == pytest.approx(
        counts["a"][0] / counts["a"][1])
    assert entry["error_halves"][1] == pytest.approx(
        counts["b"][0] / counts["b"][1])
    assert entry["n_labels_halves"] == (counts["a"][1], counts["b"][1])
    assert detail["pure_n_labels_by_state"]["s3"] == seen

    weight = float(np.log((1.0 - expected) / expected))
    threshold = detail["pure_threshold_by_state"]["s3"]
    assert abs(threshold) < 1.0
    assert np.allclose(np.abs(llr), weight)
    assert np.array_equal(llr > 0, score > threshold)
    assert detail["n_calibrated"] == score.size
    assert detail["pure_erased_cells"] == 0
    # F2: the tile's own scores are exactly ±1, so the self fit reads a
    # separation and the halo's measured error is the floor that binds
    assert entry["self_error"] < 1e-3 and entry["self_reason"] == "fitted"
    assert entry["price_source"] == pure.PRICE_FLOOR
    assert detail["pure_price_by_state"]["s3"] == {
        "self": entry["self_error"], "floor": pytest.approx(expected),
        "adopted": pytest.approx(expected)}


def test_a_separable_score_is_floored_and_a_shuffled_one_is_capped():
    """Neither end of the clamp is a pin from a sweep: it is the refusal
    to claim certainty from a finite sample, and the refusal to claim a
    direction from a filter that has none."""
    frame, lfp, cells, folds = _state_world()
    bits = np.asarray(frame.bits[:, 0], np.uint8)
    clean = np.where(bits == 1, 1.0, -1.0)
    llr, detail = pure.pure_llr(clean, frame, 0, lfp, folds)
    assert detail["pure_populations"]["s3"]["error_raw"] == 0.0
    assert detail["pure_error_by_state"]["s3"] == pure.ERROR_FLOOR
    assert np.allclose(np.abs(llr), FLOOR_WEIGHT)
    assert FLOOR_WEIGHT == pytest.approx(4.5951, abs=1e-4)

    rng = np.random.default_rng(7)
    noise = rng.normal(0.0, 1.0, bits.size)
    llr, detail = pure.pure_llr(noise, frame, 0, lfp, folds)
    assert detail["pure_populations"]["s3"]["error_raw"] > 0.45
    assert detail["pure_error_by_state"]["s3"] == pure.ERROR_CEILING
    assert np.allclose(np.abs(llr), CEILING_WEIGHT)
    assert CEILING_WEIGHT == pytest.approx(0.2007, abs=1e-4)


def test_the_halves_are_the_patch_cross_fit_halves_and_not_the_folds():
    """A fitted score's fit-fold rows carry OUT-OF-FOLD scores from the
    filter fitted on the other half (`patch`, ruling 7); the threshold
    has to travel the same way or the number is not held out."""
    frame, lfp, cells, folds = _state_world()
    score, _flip = _flipped_score(frame, folds, cells)
    detail = pure.pure_llr(score, frame, 0, lfp, folds)[1]
    train = np.asarray(frame.known[:, 0], bool) & folds.fit
    half = _halves(cells, folds)
    assert detail["pure_populations"]["s3"]["n_labels_halves"] == (
        int(np.count_nonzero(train & half)),
        int(np.count_nonzero(train & ~half)))
    # the salt is what makes them independent of fit/search/select
    plain = cal.fold_hash(cells, int(folds.seed)) < 0.5
    assert not np.array_equal(half, plain)
    assert 0.4 < float(np.mean(half)) < 0.6


def test_a_population_with_no_measurable_error_falls_back_to_the_pooled_one():
    """One label of one class in a state is not a measurement; the pooled
    population is, and the row says which priced the cells."""
    frame, lfp, cells, folds = _state_world(n=1200, state=3)
    # a second state with a single labelled cell: below the per-half floor
    bits = np.asarray(frame.bits, np.uint8).copy()
    known = np.asarray(frame.known, bool).copy()
    left, right = statecal.spectral.siblings_of(0)
    starved = np.flatnonzero(known[:, 0])[:3]
    bits[starved, left] = 0                      # state 3 -> state 2
    known[starved[1:], 0] = False                # ... one label left
    frame = dc_replace(frame, bits=bits, known=known,
                       labels=known[:, 0].copy())
    score = np.where(bits[:, 0] == 1, 1.0, -1.0)
    llr, detail = pure.pure_llr(score, frame, 0, lfp, folds)

    starved_entry = detail["pure_populations"]["s2"]
    assert starved_entry["n_labels"] <= 1
    assert starved_entry["reason"].startswith("pooled:")
    assert starved_entry["priced_by"] == pure.POOLED
    assert "s2" in detail["pure_fallback_states"]
    assert detail["pure_error_by_state"]["s2"] == detail["pure_pooled"][
        "error"]
    assert starved_entry["floor"] == detail["pure_pooled"]["error"]
    # three cells are no population OF ITS OWN, so the TILE's pooled fit
    # stands in for it (follow-up review) — never the halo's optimism at
    # full weight.  Here the filter is perfect, so the floor still binds.
    assert starved_entry["self_reason"] == "tile:below_self_min_cells"
    assert starved_entry["self_error"] < 0.01
    assert starved_entry["price_source"] == pure.PRICE_FLOOR
    assert detail["pure_floor_only_cargo_cells"] == 0
    # every cell of the starved state is still priced, at the pooled rate
    state = statecal.sibling_state(frame, 0)
    assert np.all(llr[state == 2] != 0.0)
    assert detail["pure_erased_cells"] == 0


def test_cells_nothing_prices_are_erasures_and_are_counted():
    """No label anywhere -> no error rate -> LLR 0, the erasure spelling,
    and the counts say how much of the tile went out unpriced."""
    frame, lfp, cells, folds = _state_world(n=800, known_fraction=0.0)
    known = np.zeros_like(np.asarray(frame.known, bool))
    frame = dc_replace(frame, known=known, labels=known[:, 0].copy(),
                       siblings=np.zeros(known.shape[0], bool),
                       regressors=known.all(axis=1))
    score = np.linspace(-1.0, 1.0, known.shape[0])
    llr, detail = pure.pure_llr(score, frame, 0, lfp, folds)
    assert not np.any(llr)
    assert detail["n_calibrated"] == 0
    assert detail["pure_erased_cells"] == known.shape[0]
    assert detail["pure_unknown_state_cells"] == known.shape[0]
    assert set(detail["pure_populations"]) == {"s0", "s1", "s2", "s3"}
    assert all(source is None
               for source in detail["pure_price_source"].values())
    assert all(entry["priced_by"] is None
               for entry in detail["pure_populations"].values())
    assert detail["pure_fallback_states"] == ()
    assert detail["label_rows"].size == 0
    assert detail["heldout_logloss_select"] is None

    # an unobserved or NaN-scored cell is an erasure for the same reason
    frame, lfp, cells, folds = _state_world(n=1200)
    score = np.where(frame.bits[:, 0] == 1, 1.0, -1.0)
    score[:100] = np.nan
    observed = np.asarray(lfp.observed, bool).copy()
    observed[100:200] = False
    llr, detail = pure.pure_llr(score, frame, 0,
                                dc_replace(lfp, observed=observed), folds)
    assert not np.any(llr[:200]) and np.all(llr[200:] != 0.0)
    assert detail["n_observed"] == 1100          # the 100 unobserved rows
    assert detail["n_calibrated"] == 1000        # ... and the 100 NaN ones


def test_word_sites_leave_the_error_measurement_and_the_knob_puts_them_back():
    """Ruling 11 again: a word site carries ONE target class per sibling
    state, so it cannot price the state it sits in."""
    frame, lfp, cells, folds = _state_world(n=2000, word_every=3)
    score, _flip = _flipped_score(frame, folds, cells)
    without = pure.pure_llr(score, frame, 0, lfp, folds)[1]
    with_them = pure.pure_llr(score, frame, 0, lfp, folds,
                              spec=pure.PureSpec(exclude_word_sites=False))[1]
    word = np.asarray(frame.furniture_kind, np.int8) == \
        statecal.FURNITURE_WORD
    train = np.asarray(frame.known[:, 0], bool) & folds.fit
    assert without["pure_n_labels_by_state"]["s3"] == int(
        np.count_nonzero(train & ~word))
    assert with_them["pure_n_labels_by_state"]["s3"] == int(
        np.count_nonzero(train))
    assert without["pure_exclude_word_sites"] is True


def test_soft_scales_the_magnitude_and_never_exceeds_the_hard_price():
    frame, lfp, cells, folds = _state_world()
    rng = np.random.default_rng(5)
    bits = np.asarray(frame.bits[:, 0], np.uint8)
    score = np.where(bits == 1, 1.0, -1.0) + rng.normal(0.0, 0.6, bits.size)
    hard, hard_detail = pure.pure_llr(score, frame, 0, lfp, folds)
    soft, soft_detail = pure.pure_llr(score, frame, 0, lfp, folds,
                                      spec=pure.PureSpec(soft=True))
    assert hard_detail["pure_soft"] is False and soft_detail["pure_soft"]
    assert hard_detail["pure_error_by_state"] == soft_detail[
        "pure_error_by_state"]                      # the rate is the same
    assert np.all(np.abs(soft) <= np.abs(hard) + 1e-12)
    assert np.array_equal(np.sign(soft), np.sign(hard))
    assert float(np.abs(soft).min()) < float(np.abs(hard).min())
    # a cell three sd out is paid the full price, and no more
    far = np.abs(score - hard_detail["pure_threshold_by_state"]["s3"]) \
        > pure.SOFT_CLIP * hard_detail["pure_populations"]["s3"]["scale"]
    if np.any(far):
        assert np.allclose(np.abs(soft[far]), np.abs(hard[far]))


def test_the_pure_llr_is_deterministic_and_read_only():
    frame, lfp, cells, folds = _state_world(n=900)
    score, _flip = _flipped_score(frame, folds, cells)
    first, first_detail = pure.pure_llr(score, frame, 0, lfp, folds)
    second, second_detail = pure.pure_llr(score, frame, 0, lfp, folds)
    assert np.array_equal(first, second)
    assert first_detail["pure_error_by_state"] == second_detail[
        "pure_error_by_state"]
    assert not first.flags.writeable


def test_a_bad_error_band_is_refused_rather_than_clamped():
    for bad in ({"error_floor": 0.0}, {"error_ceiling": 0.6},
                {"error_floor": 0.5, "error_ceiling": 0.4},
                {"min_per_class_per_half": 0}, {"self_min_cells": 1},
                {"self_steps": 0}):
        with pytest.raises(pure.PureError):
            pure.PureSpec(**bad)
    with pytest.raises(pure.PureError):
        pure.self_fit(np.array([1.0, np.nan]))
    spec = pure.spec_from_knobs({"pure_self_steps": 7,
                                 "pure_self_min_cells": 50})
    assert (spec.self_steps, spec.self_min_cells) == (7, 50)
    with pytest.raises(pure.PureError):
        pure.weight_of(0.0)
    frame, lfp, cells, folds = _state_world(n=400)
    with pytest.raises(pure.PureError):
        pure.pure_llr(np.zeros(7), frame, 0, lfp, folds)


# ------------------------------------------ W8 F2: the tile prices itself

def _halo_and_tile(n: int = 4000, *, seed: int = 9, halo_sd: float = 0.3,
                   tile_shift: float = 1.0, tile_sd: float = 1.0,
                   halo_flip_every: int = 0):
    """A footprint whose LABELLED cells are the halo and whose unlabelled
    cells are the tile's cargo — two populations with different
    separations, so the halo's error and the tile's are not the same
    number.  Halo scores: ±1 + N(0, halo_sd), every `halo_flip_every`-th
    one flipped; cargo scores: ±tile_shift + N(0, tile_sd), whose Bayes
    error at 0 is Φ(−tile_shift/tile_sd)."""
    frame, lfp, cells, folds = _state_world(n, seed=seed)
    known = np.asarray(frame.known[:, 0], bool)
    lfp = dc_replace(lfp, tile=dc_replace(lfp.tile, cargo=~known))
    rng = np.random.default_rng(seed)
    bits = np.asarray(frame.bits[:, 0], np.uint8)
    sign = np.where(bits == 1, 1.0, -1.0)
    score = np.where(known, sign + rng.normal(0.0, halo_sd, n),
                     sign * tile_shift + rng.normal(0.0, tile_sd, n))
    if halo_flip_every:
        flip = np.flatnonzero(known)[::halo_flip_every]
        score[flip] = -sign[flip] + rng.normal(0.0, halo_sd, flip.size)
    return frame, lfp, folds, score


def _bayes(shift: float, sd: float) -> float:
    return float(0.5 * math.erfc(shift / sd / math.sqrt(2.0)))


def test_unknown_state_cells_are_erasures_and_are_counted():
    """R2: "cells with unknown sibling state obviously are erasures / ie
    uncounted".  LLR 0, priced by nothing, in the count — and a labelled
    one leaves the select-fold arrays with the rest."""
    frame, lfp, cells, folds = _state_world(n=3000, state=None)
    known = np.asarray(frame.known, bool).copy()
    left, _right = statecal.spectral.siblings_of(0)
    unknown = np.arange(known.shape[0]) % 3 == 0
    known[unknown, left] = False
    frame = dc_replace(frame, known=known,
                       siblings=known[:, 1] & known[:, 2],
                       regressors=known.all(axis=1))
    score = np.where(frame.bits[:, 0] == 1, 1.0, -1.0)
    llr, detail = pure.pure_llr(score, frame, 0, lfp, folds)
    state = statecal.sibling_state(frame, 0)
    assert np.array_equal(state < 0, unknown)
    assert not np.any(llr[unknown]) and np.all(llr[~unknown] != 0.0)
    assert detail["pure_unknown_state_cells"] == int(unknown.sum())
    assert detail["pure_erased_cells"] == int(unknown.sum())
    assert detail["pure_cargo_erased_cells"] == int(unknown.sum())
    assert detail["n_calibrated"] == int((~unknown).sum())
    assert not np.any(unknown[detail["label_rows"]])
    assert set(detail["pure_populations"]) == {"s0", "s1", "s2", "s3"}
    # a labelled unknown-state cell trains no population either: the
    # states' labels sum to the known-state labelled fit rows
    train = np.asarray(frame.known[:, 0], bool) & folds.fit & ~unknown
    assert sum(detail["pure_n_labels_by_state"].values()) == int(
        train.sum())
    # ... and neither does the POOLED halo, which is what prices every
    # starved state (follow-up review): the pool IS the known-state rows
    assert detail["pure_pooled"]["n_labels"] == int(train.sum())


def test_the_pooled_halo_counts_no_unknown_state_row_either():
    """Follow-up review of F2.  An unknown-state cell is uncounted where
    it is decoded AND where it would price somebody else: moving those
    rows' scores must not move the pooled threshold by one float."""
    frame, lfp, cells, folds = _state_world(n=3000, state=None)
    known = np.asarray(frame.known, bool).copy()
    left, _right = statecal.spectral.siblings_of(0)
    unknown = np.arange(known.shape[0]) % 3 == 0
    known[unknown, left] = False
    frame = dc_replace(frame, known=known,
                       siblings=known[:, 1] & known[:, 2],
                       regressors=known.all(axis=1))
    score = np.where(frame.bits[:, 0] == 1, 1.0, -1.0)
    _llr, base = pure.pure_llr(score, frame, 0, lfp, folds)
    # in production those rows carry a DIFFERENT discriminant's scores
    # (`patch.fallback_population`), on another scale — here, +5
    shifted = score.copy()
    shifted[unknown] += 5.0
    _llr2, moved = pure.pure_llr(shifted, frame, 0, lfp, folds)
    assert moved["pure_pooled"]["threshold"] == \
        base["pure_pooled"]["threshold"]
    assert moved["pure_pooled"]["error"] == base["pure_pooled"]["error"]
    assert moved["pure_pooled"]["n_labels"] == \
        base["pure_pooled"]["n_labels"]


def test_a_well_separated_tile_prices_at_the_halo_floor():
    """The floor is a floor: a tile whose own scores are cleanly apart
    is never priced below what the halo measured — first at the clamp,
    then at a halo that measures 10 %."""
    frame, lfp, folds, score = _halo_and_tile(halo_sd=0.05, tile_shift=1.0,
                                              tile_sd=0.05)
    llr, detail = pure.pure_llr(score, frame, 0, lfp, folds)
    entry = detail["pure_populations"]["s3"]
    assert entry["error_raw"] == 0.0 and entry["self_error"] < 1e-6
    assert entry["error"] == pure.ERROR_FLOOR
    assert entry["price_source"] == pure.PRICE_FLOOR
    assert np.allclose(np.abs(llr), FLOOR_WEIGHT)

    frame, lfp, folds, score = _halo_and_tile(halo_sd=0.05, tile_shift=1.0,
                                              tile_sd=0.05, halo_flip_every=10)
    llr, detail = pure.pure_llr(score, frame, 0, lfp, folds)
    entry = detail["pure_populations"]["s3"]
    assert 0.07 < entry["error_raw"] < 0.13            # the halo's 10 %
    assert entry["self_error"] < 1e-6                  # the tile's ~0
    assert entry["error"] == pytest.approx(entry["error_raw"])
    assert entry["price_source"] == pure.PRICE_FLOOR
    assert detail["pure_price_by_state"]["s3"]["adopted"] == entry["error"]


def test_an_overlapping_tile_prices_its_own_overlap_and_not_the_halos():
    """§6.5's defect, inverted: the halo is easy (~0.04 % error, floored
    to 1 %) and the tile's cargo overlaps at a KNOWN Bayes error; the
    price is the tile's, within the fit's own scatter, and the LLR BP
    receives is that log-odds."""
    for shift, tolerance in ((1.645, 0.02), (1.036, 0.03), (0.674, 0.04)):
        bayes = _bayes(shift, 1.0)                     # 5 %, 15 %, 25 %
        frame, lfp, folds, score = _halo_and_tile(halo_sd=0.3,
                                                  tile_shift=shift)
        llr, detail = pure.pure_llr(score, frame, 0, lfp, folds)
        entry = detail["pure_populations"]["s3"]
        assert entry["error_raw"] < 0.005 and entry["floor"] == \
            pure.ERROR_FLOOR
        assert entry["self_reason"] == "fitted"
        assert entry["n_cargo"] == int(np.count_nonzero(~frame.known[:, 0]))
        assert entry["self_error"] == pytest.approx(bayes, abs=tolerance), (
            shift, entry["self_error"], bayes)
        assert entry["price_source"] == pure.PRICE_SELF
        assert entry["error"] == pytest.approx(entry["self_error"])
        assert detail["pure_price_by_state"]["s3"] == {
            "self": entry["self_error"], "floor": pure.ERROR_FLOOR,
            "adopted": entry["error"]}
        assert np.allclose(np.abs(llr), pure.weight_of(entry["error"]))
        # the fit's own boundary sits where the tile's populations meet
        assert abs(entry["self_boundary"]) < 0.15
        assert entry["self_error_at_boundary"] <= entry["self_error"] + 1e-9
        assert abs(entry["self_mu"][0] + shift) < 0.15
        assert abs(entry["self_mu"][1] - shift) < 0.15


def test_the_self_fit_is_deterministic_and_reads_a_known_overlap():
    rng = np.random.default_rng(4)
    bits = rng.integers(0, 2, 2000)
    scores = np.where(bits == 1, 1.036, -1.036) + rng.normal(0.0, 1.0, 2000)
    first = pure.self_fit(scores)
    second = pure.self_fit(scores.copy())
    assert first == second
    assert first.n == 2000 and first.mu_lo < 0.0 < first.mu_hi
    assert pure.error_at(0.0, first) == pytest.approx(0.15, abs=0.03)
    # a threshold off the boundary is priced for what it costs there
    assert pure.error_at(0.5, first) > pure.error_at(0.0, first)
    # the recipe: `patch`'s init and refusal floor, the step count raised
    assert pure.SELF_INIT_PERCENTILES == patch_mod.MIXTURE_INIT_PERCENTILES
    assert pure.SELF_MIN_CELLS == patch_mod.MIXTURE_MIN_CELLS
    assert pure.SELF_STEPS > patch_mod.MIXTURE_STEPS
    # one population — no filter — reads near chance, never confident
    lone = pure.self_fit(rng.normal(0.0, 1.0, 2000))
    assert pure.error_at(0.0, lone) > 0.3
    # a NaN-free fit is exact under a repeat call of the whole path
    frame, lfp, folds, score = _halo_and_tile(n=1500)
    one = pure.pure_llr(score, frame, 0, lfp, folds)
    two = pure.pure_llr(score, frame, 0, lfp, folds)
    assert np.array_equal(one[0], two[0])
    assert one[1]["pure_price_by_state"] == two[1]["pure_price_by_state"]


def test_the_self_fit_has_no_labels_and_no_fold_in_it():
    """The tile's cargo is read as scores only: permuting the target
    plane's bits on every cargo cell changes nothing about the price,
    and the fold assignment of a cargo cell is never consulted."""
    frame, lfp, folds, score = _halo_and_tile(n=2000, tile_shift=1.036)
    base = pure.pure_llr(score, frame, 0, lfp, folds)[1]
    cargo = ~np.asarray(frame.known[:, 0], bool)
    bits = np.asarray(frame.bits, np.uint8).copy()
    rng = np.random.default_rng(6)
    rows = np.flatnonzero(cargo)
    bits[rows, 0] = bits[rng.permutation(rows), 0]
    permuted = pure.pure_llr(score, dc_replace(frame, bits=bits), 0, lfp,
                             folds)[1]
    assert permuted["pure_price_by_state"] == base["pure_price_by_state"]
    assert permuted["pure_populations"]["s3"]["self_mu"] == \
        base["pure_populations"]["s3"]["self_mu"]
    other_folds = cal.split_folds(np.asarray(lfp.tile.page_cells_yx),
                                  SEED + 1)
    refolded = pure.pure_llr(score, frame, 0, lfp, other_folds)[1]
    assert refolded["pure_populations"]["s3"]["self_mu"] == \
        base["pure_populations"]["s3"]["self_mu"]


def test_a_state_that_owns_no_cell_of_the_tile_claims_no_price():
    """Follow-up review: `pure_fallback_states` was the §6.5 signal, so a
    state that priced NOTHING may not appear in it, and its record may
    not claim a pooled price that reached no cell."""
    frame, lfp, folds, score = _halo_and_tile()
    _llr, detail = pure.pure_llr(score, frame, 0, lfp, folds)
    assert detail["pure_fallback_states"] == ()
    for name in ("s0", "s1", "s2"):
        entry = detail["pure_populations"][name]
        assert entry["n_cells"] == 0
        assert entry["priced_by"] is None and entry["price_source"] is None
    assert detail["pure_populations"]["s3"]["n_cells"] == score.size


def test_a_state_too_small_to_fit_takes_the_tiles_pooled_self_price():
    """Follow-up review: a KNOWN state with too few cargo cells of its
    own is not handed the halo's floor at full weight.  The tile's whole
    known-state cargo is fitted as one population — smeared across the
    states, so pessimistic — and read at the state's own threshold."""
    frame, lfp, cells, folds = _state_world(n=4000, state=None)
    known = np.asarray(frame.known[:, 0], bool)
    lfp = dc_replace(lfp, tile=dc_replace(lfp.tile, cargo=~known))
    rng = np.random.default_rng(11)
    sign = np.where(frame.bits[:, 0] == 1, 1.0, -1.0)
    score = np.where(known, sign + rng.normal(0.0, 0.3, 4000),
                     sign * 1.036 + rng.normal(0.0, 1.0, 4000))
    # every state's OWN cargo is ~500 cells; the tile's is ~2000
    spec = pure.PureSpec(self_min_cells=800)
    _llr, detail = pure.pure_llr(score, frame, 0, lfp, folds, spec=spec)
    for name in ("s0", "s1", "s2", "s3"):
        entry = detail["pure_populations"][name]
        assert 0 < entry["n_cargo"] < 800            # its own fit refused
        assert entry["self_reason"] == "tile:below_self_min_cells"
        assert entry["self_error"] == pytest.approx(_bayes(1.036, 1.0),
                                                    abs=0.05)
        assert entry["error"] == pytest.approx(entry["self_error"])
        assert entry["price_source"] == pure.PRICE_SELF
    assert detail["pure_floor_only_cargo_cells"] == 0

    # and when the TILE cannot be fitted either, the floor is all there
    # is — and the ledger counts the cargo cells it covered
    starved = pure.PureSpec(self_min_cells=5000)
    _llr2, floored = pure.pure_llr(score, frame, 0, lfp, folds, spec=starved)
    assert all(source == pure.PRICE_FLOOR_ONLY + "below_self_min_cells"
               for source in floored["pure_price_source"].values())
    assert floored["pure_floor_only_cargo_cells"] == int((~known).sum())


def test_pseudo_trained_rows_are_subtracted_from_the_self_population():
    """R3, follow-up review: a filter measured on the cells that trained
    it reads its own error low — "ruling 7 one stage down" — so the self
    price never reads a row the decoder's pseudo labels trained on."""
    frame, lfp, folds, score = _halo_and_tile(n=2000, tile_shift=1.036)
    cargo = np.flatnonzero(np.asarray(lfp.tile.cargo, bool))
    trained = cargo[::2]
    base = pure.pure_llr(score, frame, 0, lfp, folds,
                         pseudo_rows=trained)[1]
    # the same population, reached by taking those rows out of the tile
    kept = np.zeros(score.size, bool)
    kept[cargo] = True
    kept[trained] = False
    trimmed = dc_replace(lfp, tile=dc_replace(lfp.tile, cargo=kept))
    control = pure.pure_llr(score, frame, 0, trimmed, folds)[1]
    for key in ("n_cargo", "self_error", "self_mu"):
        assert base["pure_populations"]["s3"][key] == \
            control["pure_populations"]["s3"][key]
    assert base["pure_self_excluded_cells"] == trained.size
    assert pure.pure_llr(score, frame, 0, lfp, folds)[1][
        "pure_self_excluded_cells"] == 0


# ------------------------------------------- the arbitration reads it

def test_the_select_fold_arrays_are_the_pure_llr_so_select_arm_is_unchanged():
    """Build spec item 6: with the calibration bypassed the select-fold
    loss IS the pure LLR's log loss on the select-fold labels."""
    frame, lfp, cells, folds = _state_world(n=6000, state=None,
                                            known_fraction=0.6)
    good, good_detail = pure.pure_llr(
        _flipped_score(frame, folds, cells)[0], frame, 0, lfp, folds)
    rng = np.random.default_rng(2)
    weak, weak_detail = pure.pure_llr(
        np.where(frame.bits[:, 0] == 1, 1.0, -1.0)
        + rng.normal(0.0, 2.5, cells.shape[0]), frame, 0, lfp, folds)

    rows = good_detail["label_rows"]
    assert np.array_equal(good_detail["label_llr"], good[rows])
    assert np.array_equal(good_detail["label_values"],
                          np.asarray(frame.bits[rows, 0], np.uint8))
    assert np.array_equal(rows, np.flatnonzero(
        np.asarray(frame.known[:, 0], bool) & folds.select))
    assert np.array_equal(good_detail["label_state"],
                          statecal.sibling_state(frame, 0)[rows])
    loss = float(np.mean(cal._per_label_loss(
        good_detail["label_llr"], good_detail["label_values"])))
    assert good_detail["heldout_logloss_select"] == pytest.approx(loss)

    def evidence(arm: str, detail: dict) -> Evidence:
        return Evidence(key=(0, 0, 0, "C"), lane=("cap", 0), arm=arm,
                        llr_sequential=np.zeros(4),
                        observed=np.zeros(4, bool),
                        blind={**detail, "register_arm": "committed"})

    winner, choice = cal.select_arm(
        [evidence("patch+committed", weak_detail),
         evidence("patch+field2", good_detail)], folds)
    assert winner.arm == "patch+field2"
    assert choice["comparisons"]["patch+field2"]["adopted"] is True
    assert choice["selection_refused"] is False


# ------------------------------------------------- on real (synthetic) pixels

@pytest.fixture(scope="module")
def pixels() -> World:
    return World()


def test_the_pure_price_of_the_patch_score_beats_chance_and_tracks_the_map(
        pixels):
    """The B1 filter's own score, priced both ways on the same cells."""
    score, _patch_detail = pixels.score()
    pure_llr, pure_detail = pure.pure_llr(score, pixels.frame, 0,
                                          pixels.lfp, pixels.folds)
    pava_llr, pava_detail = cal.calibrate(score, pixels.frame, 0, pixels.lfp,
                                          pixels.folds, branches="state",
                                          stream_id="C")
    rows = pure_detail["label_rows"]
    truth = np.asarray(pixels.frame.bits[rows, 0], np.uint8)
    print()
    print(f"pure  select log loss {pure_detail['heldout_logloss_select']:.4f}"
          f"  errors {pure_detail['pure_error_by_state']}")
    print(f"pava  select log loss {pava_detail['heldout_logloss_select']:.4f}")
    assert pure_detail["heldout_logloss_select"] < np.log(2.0)
    assert float(np.mean((pure_llr[rows] > 0) == (truth == 1))) > 0.95
    shared = np.intersect1d(rows, pava_detail["label_rows"])
    assert float(np.mean((pure_llr[shared] > 0)
                         == (pava_llr[shared] > 0))) > 0.98
    assert pure_detail["pure_erased_cells"] == 0
    for name in ("s0", "s1", "s3"):
        entry = pure_detail["pure_populations"][name]
        assert entry["reason"] == "measured"
        # the self fit ran on the tile's own cargo (~800-1900 cells per
        # state here) and read a separated population
        assert entry["self_reason"] == "fitted" and entry["n_cargo"] > 500
        assert entry["self_error"] < 0.05
        assert entry["error"] >= entry["floor"]


def test_shuffled_fit_labels_are_priced_at_chance_not_at_confidence(pixels):
    """The blind twin of MEAS §5b's permutation control, one layer on:
    the filter collapses AND the price collapses with it — the ceiling is
    what stops a dead filter from shouting."""
    bits = np.asarray(pixels.frame.bits, np.uint8).copy()
    fit_rows = np.flatnonzero(pixels.frame.known[:, 0] & pixels.folds.fit)
    rng = np.random.default_rng(1)
    bits[fit_rows, 0] = bits[rng.permutation(fit_rows), 0]
    shuffled = dc_replace(pixels.frame, bits=bits)
    score, _detail = pixels.score(frame=shuffled)
    llr, detail = pure.pure_llr(score, shuffled, 0, pixels.lfp, pixels.folds)
    for name in ("s0", "s1", "s3"):
        entry = detail["pure_populations"][name]
        assert entry["error"] == pure.ERROR_CEILING
        # F2: the dead filter's scores on its OWN tile are one population,
        # and the equal-prior fit reads them near chance.  This says the
        # price COLLAPSES with the filter; it does not by itself say the
        # price read no label — a supervised price would also land near
        # chance here.  The leak detector is the cargo permutation in
        # `test_the_self_fit_has_no_labels_and_no_fold_in_it`, and the
        # structural guard is `frame`'s own cargo-known assertion.
        assert entry["self_error"] > 0.25, (name, entry["self_error"])
        assert entry["price_source"] == pure.PRICE_FLOOR    # the cap binds
    assert float(np.abs(llr).max()) == pytest.approx(CEILING_WEIGHT)
    true_bits = np.asarray(pixels.frame.bits[:, 0], np.uint8)
    rows = detail["label_rows"]
    accuracy = float(np.mean((llr[rows] > 0) == (true_bits[rows] == 1)))
    assert 0.4 < accuracy < 0.6                         # chance, both ways


def _pixel_run(world: World, monkeypatch, arm: str, knobs: dict):
    """`evidence_for` end to end on the synthetic page (B4's harness)."""
    row = row_of(R0850)
    inputs = _FakeInputs(row, frame_mod.geometry_of(row))

    def fake_known_frame(_inputs, _certs, fp_, target, *, metadata_known,
                         metadata_bit=None):
        assert np.array_equal(fp_.page_cells_yx, world.fp.page_cells_yx)
        return dc_replace(world.frame, target=target)

    monkeypatch.setattr(arms_mod.frame_mod, "known_frame", fake_known_frame)
    return arms_mod.evidence_for(
        inputs, {}, (0, 0, 0, "C"), world.lane, arm, halo_cells=HALO,
        knobs={"seed": SEED, "ctx_mode": "none",
               "mix_scope_ladder": ("footprint",),
               "metadata_known": False, **knobs})


def test_the_hook_replaces_the_whole_calibration_stage_and_says_so(
        pixels, monkeypatch):
    """`calibration=pure` in the knob bag is the only door; the row that
    comes back carries the pure record and none of the map's."""
    pure_evidence = _pixel_run(pixels, monkeypatch, "patch+committed",
                               {"calibration": "pure"})
    blind = pure_evidence.blind
    assert blind.get("refusal") is None
    assert blind["calibration"] == "pure"
    assert set(blind["pure_error_by_state"]) == {"s0", "s1", "s2", "s3"}
    assert set(blind["pure_price_by_state"]) == set(blind["pure_price_source"])
    assert all(set(price) == {"self", "floor", "adopted"}
               for price in blind["pure_price_by_state"].values())
    assert "pure_erased_cells" in blind and "refit" not in blind
    assert blind["patch_fitted_states"]              # the filter still ran
    assert "branches" not in blind and "branch_fallback" not in blind
    assert blind["ctx_adopted"] is False
    assert np.any(pure_evidence.observed)
    assert np.any(pure_evidence.llr_sequential[pure_evidence.observed])
    prices = np.unique(np.abs(pure_evidence.llr_sequential[
        pure_evidence.observed]))
    assert prices.size <= len(blind["pure_error_by_state"]) + 1

    mapped = _pixel_run(pixels, monkeypatch, "patch+committed", {})
    assert "calibration" not in mapped.blind
    assert "branches" in mapped.blind
    assert set(np.unique(np.abs(mapped.llr_sequential))).__len__() > 8
    # same arm, same pixels, same cells observed — only the price differs
    assert np.array_equal(mapped.observed, pure_evidence.observed)
    agree = ((mapped.llr_sequential > 0) == (pure_evidence.llr_sequential > 0))
    assert float(np.mean(agree[pure_evidence.observed])) > 0.95


# ---------------------------------------------------------- the profiles

def test_the_three_pure_profiles_name_the_pure_path_and_nothing_else():
    for name in ("pure", "pure-self", "pure-refit"):
        profile = PROFILES[name]
        assert profile["arms"] == ("patch+field2", "patch+committed"), name
        assert profile["rules"] == ("sum",), name
        assert profile["reroll"] is False, name
        assert profile["ctx_mode"] == "none", name
        for arm in profile["arms"]:
            head, tail = arms_mod.parse_arm(arm)
            assert head in patch_mod.PATCH_MODES
            assert tail in arms_mod.REGISTER_ARMS
        config = with_profile(AnalyzerConfig(), name)
        assert config.knobs_from == f"profile:{name}"
        assert pure.is_pure(config.knobs)
        assert config.knobs["patch_train_scope"] == "local5"
        assert config.knobs["patch_samples_per_cell"] == 16
        assert config.battery_for("C") == profile["arms"]
        # no PAVA branch, no state context, no Platt: the pure path's
        # whole point is that none of them is between filter and BP
        assert "branches" not in config.knobs
        assert "ctx_state" not in config.knobs
        assert "platt-state" not in config.rules

    assert PROFILES["pure"]["rungs"] == ("L0", "L1", "L2")
    assert "patch_selftrain_rounds" not in PROFILES["pure"]["knobs"]
    assert PROFILES["pure-self"]["knobs"]["patch_selftrain_rounds"] == 4
    assert PROFILES["pure-refit"]["knobs"]["patch_selftrain_rounds"] == 4
    assert PROFILES["pure-refit"]["rungs"] == ("L0", "L1", "L2", "L3f")
    # and no profile that existed before P0 learned about it
    for name in ("wide-halo", "battery", "everything",
                 "patch", "patch-self", "patch-refit", "everything+patch"):
        assert not pure.is_pure(PROFILES[name].get("knobs", {})), name


def test_a_pass_under_the_pure_profile_records_it_in_the_ledger_header(
        monkeypatch):
    """The acceptance leg: the driver runs the profile end to end (every
    decision stubbed) and the header says which configuration ran."""
    keys = [(0, 0, 0, "C"), (0, 0, 1, "C")]
    _stubbed_driver(monkeypatch, certify={keys[0]}, follow_ups={})
    config = with_profile(AnalyzerConfig(workers=1, max_generations=1),
                          "pure")
    ledger = fp.run(_FakeRun(), keys, config)
    header = ledger.header
    assert header["knobs_from"] == "profile:pure"
    assert header["knobs"]["calibration"] == "pure"
    assert header["arms"] == ["patch+field2", "patch+committed"]
    assert header["rules"] == ["sum"] and header["rungs"] == ["L0", "L1",
                                                              "L2"]
    assert header["ctx_mode"] == "none"
    assert header["n_certified"] == 1


# -------------------------------------------- W8 B8: the pure path, PLACED

def _placement_world(monkeypatch, *, certify_arm: str):
    """One lane; only `certify_arm`'s evidence carries the frame.

    `_reroll_world`'s pattern (test_analyzer_gaps_fix), with the arms
    every call asks for RECORDED — which is the whole question here: a
    re-roll-only arm must not be computed on a key the battery closes.
    """
    from .test_analyzer_gaps_fix import _FakeLane
    from ._synthetic import build_frame

    built = build_frame(R0850, key=(0, 12, 7, "C"), seed=5)
    inputs = _FakeInputs(row_of(R0850), frame_mod.geometry_of(row_of(R0850)))
    good = np.where(np.asarray(built.printed, np.uint8) > 0, 6.0, -6.0)
    asked: list[str] = []

    def fake_lanes(_inputs, _page, _ty, _tx, cover_fraction=0.9):
        return [_FakeLane()]

    def fake_evidence(_inputs, _certs, key, lane, arm, *, halo_cells=None,
                      knobs=None, crop_memo=None):
        asked.append(arm)
        values = good if arm == certify_arm else np.zeros(good.size)
        return Evidence(key=key, lane=lane.lane_id, arm=arm,
                        llr_sequential=np.asarray(values, np.float64),
                        observed=np.ones(values.size, bool),
                        blind={"arm": arm})

    monkeypatch.setattr(fp.sample_mod, "lanes_for_tile", fake_lanes)
    monkeypatch.setattr(fp.arms_mod, "evidence_for", fake_evidence)
    return inputs, built, asked


def _placement_config(**overrides) -> AnalyzerConfig:
    return AnalyzerConfig(arms=("subtract+offset",), rules=("sum",),
                          rungs=("L0",), reroll=True, all_rules=False,
                          reroll_only_arms=("pure+committed",), **overrides)


def test_a_placed_arm_is_never_computed_for_a_key_the_battery_closes(
        monkeypatch):
    """The user's ruling (b): "only run it after the other pass has done
    its job".  The battery certifies, and the pure arm costs nothing."""
    inputs, built, asked = _placement_world(monkeypatch,
                                            certify_arm="subtract+offset")
    out = fp.blind_key(inputs, {}, built.key, _placement_config(),
                       fp.shared_exposure())
    assert out.get("user_bits") is not None
    assert out["certifying_arm"] == "subtract+offset"
    assert asked == ["subtract+offset"]          # the pure arm never ran
    assert "reroll" not in out


def test_a_placed_arm_runs_and_is_attributed_when_the_battery_leaves_it_open(
        monkeypatch):
    """... and when the battery fails, the placed arm is the re-roll."""
    inputs, built, asked = _placement_world(monkeypatch,
                                            certify_arm="pure+committed")
    out = fp.blind_key(inputs, {}, built.key, _placement_config(),
                       fp.shared_exposure())
    assert out.get("user_bits") is not None
    assert out["certifying_arm"] == "reroll:pure+committed"
    assert out["certifying_rule"] == "sum|reroll:pure+committed"
    assert asked == ["subtract+offset", "pure+committed"]
    assert out["reroll"]["deferred"] == ["pure+committed"]
    assert out["reroll"]["arms"] == ["pure+committed"]
    # the placed arm's blind record is in the row like any other arm's
    assert ("l0", "pure+committed") in out["evidence"] or any(
        arm == "pure+committed" for _lane, arm in out["evidence"])
    assert np.array_equal(np.asarray(out["user_bits"], np.uint8),
                          np.asarray(built.user, np.uint8))


def test_a_placed_arm_is_not_a_selection_candidate(monkeypatch):
    """It cannot win the select fold, because it is not in the battery."""
    inputs, built, asked = _placement_world(monkeypatch,
                                            certify_arm="pure+committed")
    config = _placement_config()
    assert config.battery_for("C") == ("subtract+offset",)
    assert config.reroll_battery_for("C") == ("pure+committed",)
    fp.blind_key(inputs, {}, built.key, config, fp.shared_exposure())
    assert asked[0] == "subtract+offset"
    # a name means ONE placement: an arm already in the battery is dropped
    both = dc_replace(config, arms=("subtract+offset", "pure+committed"))
    assert both.reroll_battery_for("C") == ()
    # ... and the re-roll switch still governs it
    off = dc_replace(config, reroll=False)
    inputs, built, asked = _placement_world(monkeypatch,
                                            certify_arm="pure+committed")
    out = fp.blind_key(inputs, {}, built.key, off, fp.shared_exposure())
    assert out.get("user_bits") is None and asked == ["subtract+offset"]


def test_the_placement_profiles_are_their_parents_plus_the_pure_arms():
    """X7/X8: one variable — the calibration — and nothing else moves."""
    for name, parent in (("patch-then-pure", "patch-refit"),
                         ("everything+patch+pure", "everything+patch")):
        profile, base = PROFILES[name], PROFILES[parent]
        assert profile["reroll_only_arms"] == ("pure+committed",
                                               "pure+field2")
        for field in ("arms", "rules", "rungs", "knobs", "halo_cells",
                      "reroll_rungs"):
            assert profile[field] == base[field], (name, field)
        assert base.get("reroll_only_arms", ()) == ()
        for arm in profile["reroll_only_arms"]:
            head, tail = arms_mod.parse_arm(arm)
            assert head == patch_mod.UNMIX_PURE
            assert tail in arms_mod.REGISTER_ARMS
        config = with_profile(AnalyzerConfig(), name)
        assert config.reroll is True
        assert config.reroll_only_arms == profile["reroll_only_arms"]
        assert not any(arm.startswith("pure+")
                       for arm in config.battery_for("C"))
        assert config.reroll_battery_for("C") == profile["reroll_only_arms"]
        # the knob bag does NOT carry `calibration`: the ARM names it, so
        # the battery's own patch arms keep the map
        assert not pure.is_pure(config.knobs)
        assert pure.is_pure(config.knobs, patch_mod.UNMIX_PURE)
    # every profile that existed before B8 places nothing
    for name, profile in PROFILES.items():
        if name in ("patch-then-pure", "everything+patch+pure"):
            continue
        assert profile.get("reroll_only_arms", ()) == (), name
    assert AnalyzerConfig().reroll_only_arms == ()


def test_the_header_says_which_arms_were_placed(monkeypatch):
    keys = [(0, 0, 0, "C")]
    _stubbed_driver(monkeypatch, certify=set(), follow_ups={})
    config = with_profile(AnalyzerConfig(workers=1, max_generations=1),
                          "patch-then-pure")
    header = fp.run(_FakeRun(), keys, config).header
    assert header["reroll_only_arms"] == ["pure+committed", "pure+field2"]
    assert "pure+committed" not in header["arms"]
    assert header["knobs_from"] == "profile:patch-then-pure"


# ------------------------------------------------------------- blindness

def test_pure_is_blind_and_imports_no_module_that_dispatches_into_it():
    tree = ast.parse(pathlib.Path(pure.__file__).read_text("utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    assert not any("truth" in name or "oracle" in name or name == "score"
                   for name in names), sorted(names)
    assert "arms" not in names and "unmix" not in names
    assert "refit" not in names                    # R3: no refit in here
    assert {"calibrate", "patch", "statecal"} <= names

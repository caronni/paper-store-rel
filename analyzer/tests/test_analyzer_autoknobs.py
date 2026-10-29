"""W8 B7 — `analyzer.autoknobs`: the knobs a run chooses for itself.

The user's ruling of 2026-09-06 is that no default in the patch family
may be a number carried over from a sweep on one sheet: where a run can
decide from the sheet in front of it, it must.  What is pinned here is
therefore the ARBITRATION, not any value — that a clearly better
candidate is adopted, that an undiscriminating select fold leaves every
axis where it was, that a memorising filter is refused by its own
cross-fit numbers, and that shuffled labels read chance through the whole
chain.  Every fixture is synthetic and fast.
"""

from __future__ import annotations

import ast
import pathlib

import numpy as np
import pytest

from holo.receiver.lib import pava
from holo.receiver.plugins import color_region_anchor as anchor

from analyzer import (autoknobs, calibrate as cal, patch as patch_mod,
                      patchcache, sample)
from analyzer.tests._patch_world import CELL_DOTS, PITCH_PX, World


@pytest.fixture(scope="module")
def world() -> World:
    """The B1 synthetic page — a flat third-layer deficit on M+Y cells,
    a dot core everywhere else — reused so this file stays fast."""
    return World()


# ------------------------------------------------------------ the sentinel

def test_auto_is_one_spelling_and_every_knob_that_takes_it_is_named():
    assert autoknobs.AUTO == "auto"
    for spelling in ("auto", "AUTO", " Auto "):
        assert autoknobs.is_auto(spelling)
    for other in (None, 8, 1.5, "automatic", "", (0,), True):
        assert not autoknobs.is_auto(other)
    # the knob names and the axes they resolve line up one for one
    assert set(autoknobs.AUTO_KNOBS) == {
        "patch_" + name for name in autoknobs.CANDIDATES} | {
        "patch_min_labels_per_state", "patch_min_labels_agnostic",
        "aperture_cells"}
    assert autoknobs.APERTURE_CANDIDATES[1] == float(anchor.APERTURE_CELLS)


# ------------------------------------------------- the select-fold losses

def _scores(rng, n, separation):
    labels = (rng.random(n) < 0.5).astype(np.uint8)
    return labels, rng.normal(0.0, 1.0, n) + separation * labels


def test_select_losses_are_per_label_and_refuse_below_the_pava_floors():
    rng = np.random.default_rng(4)
    labels, scores = _scores(rng, 400, 3.0)
    train, evaluate = slice(0, 300), slice(300, 400)
    losses = autoknobs.select_losses(scores[train], labels[train],
                                     scores[evaluate], labels[evaluate])
    assert losses is not None and losses.shape == (100,)
    assert float(np.mean(losses)) < 0.35             # a real separation
    # a score that carries nothing reads CHANCE, and is not a refusal
    noise = rng.normal(0.0, 1.0, 400)
    chance = autoknobs.select_losses(noise[train], labels[train],
                                     noise[evaluate], labels[evaluate])
    assert chance is not None
    assert abs(float(np.mean(chance)) - float(np.log(2.0))) < 0.25
    # the floors: too few held-out labels, and a one-class training side
    assert autoknobs.select_losses(scores[train], labels[train],
                                   scores[300:305], labels[300:305]) is None
    assert autoknobs.select_losses(
        scores[train], np.ones(300, np.uint8),
        scores[evaluate], labels[evaluate]) is None
    assert pava.CAL_MIN_HELDOUT == 10 and pava.CAL_MIN_PER_CLASS == 10


def test_the_paired_verdict_adopts_only_past_the_standard_error_margin():
    rng = np.random.default_rng(5)
    base = rng.random(200) + 0.5
    same = base.copy()
    better = base - 0.4
    noise = base + rng.normal(0.0, 1.0, 200)     # same mean, huge spread
    assert autoknobs.paired_verdict(base, better)["adopted"] is True
    assert autoknobs.paired_verdict(base, same)["adopted"] is False
    assert autoknobs.paired_verdict(base, noise)["adopted"] is False
    assert autoknobs.paired_verdict(base, base + 0.4)["adopted"] is False
    short = autoknobs.paired_verdict(base[:5], better[:5])
    assert short["adopted"] is False
    assert short["reason"] == "too_few_paired_labels"


def test_the_minority_floor_counts_the_populations_own_smaller_class():
    ones = np.ones(500, np.uint8)
    assert not autoknobs.minority_ok(ones)
    mixed = ones.copy()
    mixed[:cal.SELECT_MIN_MINORITY - 1] = 0
    assert not autoknobs.minority_ok(mixed)
    mixed[:cal.SELECT_MIN_MINORITY] = 0
    assert autoknobs.minority_ok(mixed)


# ------------------------------------------------------ the coordinate pass

def _fixed_losses(table, default=0.5):
    """An `evaluate` whose loss depends only on the axes it is given."""
    calls: list[dict] = []

    def evaluate(axes):
        calls.append(dict(axes))
        key = tuple(sorted((name, _hashable(value))
                           for name, value in axes.items()))
        value = table.get(key, default)
        if value is None:
            return None
        rng = np.random.default_rng(7)
        return np.full(60, value) + 1e-6 * rng.random(60)

    return evaluate, calls


def _hashable(value):
    return tuple(value) if isinstance(value, (tuple, list)) else value


def _key(**axes):
    return tuple(sorted((name, _hashable(value))
                        for name, value in axes.items()))


def test_choose_takes_the_candidate_that_wins_and_records_every_loss():
    inherited = {"window_cells": 1.5, "shrinkage": 1e-2}
    table = {_key(window_cells=1.5, shrinkage=1e-2): 0.50,
             _key(window_cells=1.0, shrinkage=1e-2): 0.60,
             _key(window_cells=2.0, shrinkage=1e-2): 0.20,
             _key(window_cells=2.0, shrinkage=1e-3): 0.10,
             _key(window_cells=2.0, shrinkage=1e-1): 0.30}
    evaluate, calls = _fixed_losses(table)
    axes, losses, detail = autoknobs.choose(
        inherited, {"window_cells": autoknobs.WINDOW_CANDIDATES,
                    "shrinkage": autoknobs.SHRINKAGE_CANDIDATES},
        evaluate, order=("window_cells", "shrinkage"))
    assert axes == {"window_cells": 2.0, "shrinkage": 1e-3}
    assert detail["adopted"] == {"window_cells": "window_cells=2",
                                 "shrinkage": "shrinkage=0.001"}
    # the shrinkage was chosen FOR the adopted window, not for the
    # inherited one — the coordinate pass carries its choice forward
    assert {"window_cells": 2.0, "shrinkage": 1e-3} in calls
    assert set(losses) == {"inherited", "window_cells=1", "window_cells=2",
                           "shrinkage=0.001", "shrinkage=0.1"}
    assert losses["window_cells=2"] == pytest.approx(0.20, abs=1e-5)
    assert detail["n_evaluated"] == len(calls) == 5


def test_an_undiscriminating_select_fold_leaves_every_axis_inherited():
    inherited = {"window_cells": 1.5, "channels": (0,)}
    evaluate, calls = _fixed_losses({}, default=0.5)   # every candidate ties
    axes, losses, detail = autoknobs.choose(
        inherited, {"window_cells": autoknobs.WINDOW_CANDIDATES,
                    "channels": autoknobs.CHANNEL_CANDIDATES},
        evaluate, order=("window_cells", "channels"))
    assert axes == inherited
    assert detail["adopted"] == {}
    assert len(calls) == 4                       # baseline + 3 candidates
    # ... and a candidate that REFUSES is recorded as None, never adopted
    evaluate, _calls = _fixed_losses(
        {_key(window_cells=2.0, channels=(0,)): None})
    axes, losses, detail = autoknobs.choose(
        inherited, {"window_cells": autoknobs.WINDOW_CANDIDATES},
        evaluate, order=("window_cells",))
    assert losses["window_cells=2"] is None and axes == inherited


def test_choose_refuses_without_a_baseline_and_is_deterministic():
    evaluate, _calls = _fixed_losses({_key(window_cells=1.5): None})
    axes, losses, detail = autoknobs.choose(
        {"window_cells": 1.5},
        {"window_cells": autoknobs.WINDOW_CANDIDATES}, evaluate,
        order=("window_cells",))
    assert detail["refused"] == "no_baseline" and axes == {"window_cells": 1.5}
    assert losses == {}
    table = {_key(window_cells=2.0): 0.1}
    first = autoknobs.choose({"window_cells": 1.5},
                             {"window_cells": autoknobs.WINDOW_CANDIDATES},
                             _fixed_losses(table)[0], order=("window_cells",))
    second = autoknobs.choose({"window_cells": 1.5},
                              {"window_cells": autoknobs.WINDOW_CANDIDATES},
                              _fixed_losses(table)[0], order=("window_cells",))
    assert first[0] == second[0] and first[1] == second[1]


# ------------------------------------------------------- the tier admission

def _wrongs(n_insample, n_crossfit, n, ones):
    labels = np.zeros(n, np.uint8)
    labels[:ones] = 1
    insample = np.zeros(n, bool)
    insample[:n_insample] = True
    crossfit = np.zeros(n, bool)
    crossfit[:n_crossfit] = True
    return insample, crossfit, labels


def test_admit_takes_a_filter_that_generalises_and_refuses_one_that_memorises():
    # a real filter: 4 % in sample, 6 % out of fold, on a balanced pool
    insample, crossfit, labels = _wrongs(40, 60, 1000, 500)
    ok, detail = autoknobs.admit(insample, crossfit, labels)
    assert ok and detail["reason"] == "admitted"
    assert detail["error_crossfit"] == pytest.approx(0.06)
    assert detail["gap"] == pytest.approx(0.02)
    assert detail["gain"] == pytest.approx(0.44)

    # a memorising one: perfect in sample, chance out of fold
    insample, crossfit, labels = _wrongs(0, 500, 1000, 500)
    ok, detail = autoknobs.admit(insample, crossfit, labels)
    assert not ok and detail["reason"] == "crossfit_no_better_than_majority"

    # and the optimism clause: a filter that beats the majority rate a
    # little while its fit is mostly memory
    insample, crossfit, labels = _wrongs(50, 440, 1000, 500)
    ok, detail = autoknobs.admit(insample, crossfit, labels)
    assert not ok and detail["reason"] == "optimism_exceeds_the_gain"
    assert detail["gap"] > detail["gain"] > 0.0

    # the count floors, which are the only counts left in the rule
    insample, crossfit, labels = _wrongs(0, 0, 6, 3)
    ok, detail = autoknobs.admit(insample, crossfit, labels)
    assert not ok and detail["reason"] == "too_few_crossfit_labels"
    insample, crossfit, labels = _wrongs(0, 0, 40, 1)
    ok, detail = autoknobs.admit(insample, crossfit, labels)
    assert not ok and detail["reason"] == "too_few_crossfit_labels"


def test_admit_refuses_a_tier_that_reads_worse_than_what_it_displaces():
    """The third clause (review 2026-09-06).

    The two cross-fit clauses compare a filter to MAJORITY-CLASS
    GUESSING, which a filter worse than the plain `subtract` score can
    clear — and the tier ladder then hands it those cells before any
    later tier sees them.  So the caller may offer the alternative's own
    per-label losses, and a tier the alternative beats by more than the
    module's margin is refused.  Ties keep the tier: it is the arm's own
    mechanism, and `select_arm` arbitrates the whole arm afterwards.
    """
    insample, crossfit, labels = _wrongs(40, 60, 1000, 500)
    # a clearly better alternative: half the loss on every row
    good = np.full(1000, 0.20)
    poor = np.full(1000, 0.55)
    ok, detail = autoknobs.admit(insample, crossfit, labels,
                                 own_losses=poor, alternative_losses=good)
    assert not ok and detail["reason"] == "worse_than_the_alternative"
    assert detail["comparison"] == "paired_against_the_alternative"
    assert detail["comparison_n"] == 1000
    assert detail["alternative_gain"] == pytest.approx(0.35)

    # the other direction, and a tie: the tier keeps its cells
    ok, _detail = autoknobs.admit(insample, crossfit, labels,
                                  own_losses=good, alternative_losses=poor)
    assert ok
    ok, tie = autoknobs.admit(insample, crossfit, labels,
                              own_losses=good, alternative_losses=good)
    assert ok and tie["reason"] == "admitted"

    # too few paired rows: the comparison is REFUSED, never fabricated,
    # and the first two clauses decide alone
    insample, crossfit, labels = _wrongs(2, 3, 40, 20)
    ok, detail = autoknobs.admit(insample, crossfit, labels,
                                 own_losses=np.full(40, 0.9),
                                 alternative_losses=np.full(40, 0.1))
    assert detail["comparison"] == "paired_against_the_alternative"
    # ... and offering nothing leaves the rule exactly as B7 built it
    insample, crossfit, labels = _wrongs(40, 60, 1000, 500)
    ok, detail = autoknobs.admit(insample, crossfit, labels)
    assert ok and detail["comparison"] == "not_offered"


def test_crossfit_losses_prices_each_half_with_the_other_halfs_map():
    """The map is cross-fit on the halves the FILTER used (review).

    A PAVA map fitted on every out-of-fold score and priced on the same
    rows is in-sample for the map, however honest the scores are.
    """
    n = 600
    labels = np.zeros(n, np.float64)
    labels[::2] = 1.0
    half = np.zeros(n, bool)
    half[:n // 2] = True
    good = np.where(labels == 1.0, 2.0, -2.0)
    losses = autoknobs.crossfit_losses(good, labels, half)
    assert losses is not None and losses.size == n
    assert np.all(np.isfinite(losses))
    noise = np.where(np.arange(n) % 3 == 0, 1.0, -1.0)
    worse = autoknobs.crossfit_losses(noise, labels, half)
    assert worse is not None and float(np.mean(worse)) > float(
        np.mean(losses))
    # a half below `pava`'s floors is a refusal, never a number
    tiny = np.zeros(20, bool)
    tiny[:10] = True
    assert autoknobs.crossfit_losses(good[:20], labels[:20], tiny) is None


def test_admit_is_not_a_label_count_pin():
    """The same error rates decide the same way at 40 labels and at 4000.

    That is the point of B7 item (b): what admits a tier is how well it
    reads out of fold, not how many labels it happened to have.
    """
    for n in (40, 400, 4000):
        insample, crossfit, labels = _wrongs(n // 25, n // 20, n, n // 2)
        ok, detail = autoknobs.admit(insample, crossfit, labels)
        assert ok, (n, detail)
    # a filter at chance is refused at every size
    for n in (40, 400, 4000):
        insample, crossfit, labels = _wrongs(0, n // 2, n, n // 2)
        assert not autoknobs.admit(insample, crossfit, labels)[0]


# ------------------------------------------------------------- the features

def test_the_bounding_geometry_is_the_inherited_one_until_an_axis_is_auto():
    inherited = {"samples_per_cell": 8, "window_cells": 1.5,
                 "channels": (0,), "features": "pixels", "shrinkage": 1e-2}
    assert autoknobs.bounding_axes(inherited, ()) == inherited
    wide = autoknobs.bounding_axes(inherited, ("window_cells",))
    assert wide["window_cells"] == max(autoknobs.WINDOW_CANDIDATES)
    assert wide["samples_per_cell"] == 8
    fine = autoknobs.bounding_axes(inherited, ("samples_per_cell",))
    assert fine["samples_per_cell"] == max(autoknobs.SAMPLES_CANDIDATES)


def test_two_candidates_that_resolve_onto_one_grid_share_one_extraction(world):
    rows = np.flatnonzero(world.lfp.observed)[:200]
    bank = autoknobs.FeatureBank(world.crops, world.read, world.lfp, rows)
    eight = {"samples_per_cell": 8, "window_cells": 1.5, "channels": (0,),
             "features": "pixels", "shrinkage": 1e-2}
    sixteen = {**eight, "samples_per_cell": 16}
    assert bank.key(eight) == bank.key(sixteen)     # the lane is 8 px/cell
    first, _inside = bank.selection(eight)
    second, _inside = bank.selection(sixteen)
    assert first is second                          # one block, one memo
    assert bank.geometry_of(sixteen) == (int(PITCH_PX), 12)
    wide = {**eight, "window_cells": 2.0}
    assert bank.key(wide) != bank.key(eight)
    assert bank.selection(wide)[0].shape[1] == 16 * 16
    rgb = {**eight, "channels": (0, 1, 2)}
    assert bank.selection(rgb)[0].shape[1] == 3 * 12 * 12


def test_one_bounded_extraction_serves_every_narrower_candidate(world):
    """W8 B8: the walk resamples ONCE, and a slice is not an approximation.

    Every candidate of the coordinate pass is a column subset of the
    widest geometry — the centred sub-square for a narrower window, the
    leading block for `r` inside `rgb`, a matrix multiply for `rings` —
    so the whole walk costs one `map_coordinates` pass, and each sliced
    block is BYTE-IDENTICAL to a direct extraction of that candidate.
    """
    rows = np.flatnonzero(world.lfp.observed)[:120]
    base = {"samples_per_cell": 8, "window_cells": 1.5, "channels": (0,),
            "features": "pixels", "shrinkage": 1e-2}
    walk = [base, {**base, "window_cells": 1.0}, {**base, "window_cells": 2.0},
            {**base, "channels": (0, 1, 2)}, {**base, "features": "rings"}]
    widest = autoknobs.bounding_of(walk)
    assert widest["window_cells"] == 2.0 and widest["channels"] == (0, 1, 2)
    bank = autoknobs.FeatureBank(world.crops, world.read, world.lfp, rows,
                                 bounding=widest)
    plain = autoknobs.FeatureBank(world.crops, world.read, world.lfp, rows)
    for axes in walk:
        got, _inside = bank.selection(axes)
        want, _inside = plain.selection(axes)
        assert np.array_equal(got, want, equal_nan=True), axes
    assert bank.n_extractions == 1                 # the whole walk
    assert plain.n_extractions == len(walk)        # one per candidate
    bank.use_selection(rows[:50], widest)
    assert bank.selection(base)[0].shape[0] == 50
    assert bank.n_extractions == 2


def test_a_column_subset_refuses_what_it_cannot_serve(world):
    fine = {"samples_per_cell": 8, "window_cells": 1.5, "channels": (0, 1),
            "features": "pixels", "shrinkage": 1e-2}
    pitch = float(world.crops.pitch_px_level)
    assert autoknobs.column_subset(fine, fine, pitch).size == 2 * 12 * 12
    # a WIDER window, a channel the base does not carry, and a coarser
    # sampling are all refusals, never a wrong slice
    assert autoknobs.column_subset(
        fine, {**fine, "window_cells": 2.0}, pitch) is None
    assert autoknobs.column_subset(
        fine, {**fine, "channels": (2,)}, pitch) is None
    coarse = {**fine, "samples_per_cell": 4}
    assert autoknobs.column_subset(coarse, fine, pitch) is None


def test_the_inside_mask_is_the_extractors_own_predicate(world):
    """The bounds test costs one comparison per row, not one per sample."""
    rows = np.flatnonzero(world.lfp.observed)
    for window in (1.0, 1.5, 2.0):
        axes = {"samples_per_cell": 8, "window_cells": window,
                "channels": (0,), "features": "pixels", "shrinkage": 1e-2}
        grid = patch_mod.grid_cells(
            patch_mod.PatchSpec(window_cells=window, samples_per_cell=8),
            float(world.crops.pitch_px_level))
        _features, inside = patch_mod.extract(
            world.crops, world.read.points_yx, world.read.linear_by_owner,
            world.lfp.owner_index, rows, grid, (0,))
        bank = autoknobs.FeatureBank(world.crops, world.read, world.lfp)
        assert np.array_equal(bank.inside(axes, rows), inside), window
    tight = World(bound_dots=0.0)      # halo_px = 8, a real edge
    rows = np.flatnonzero(tight.lfp.observed)
    axes = {"samples_per_cell": 8, "window_cells": 2.0, "channels": (0,),
            "features": "pixels", "shrinkage": 1e-2}
    grid = patch_mod.grid_cells(
        patch_mod.PatchSpec(window_cells=2.0, samples_per_cell=8),
        float(tight.crops.pitch_px_level))
    _features, inside = patch_mod.extract(
        tight.crops, tight.read.points_yx, tight.read.linear_by_owner,
        tight.lfp.owner_index, rows, grid, (0,))
    assert not inside.all() and inside.any()       # a real crop edge
    bank = autoknobs.FeatureBank(tight.crops, tight.read, tight.lfp)
    assert np.array_equal(bank.inside(axes, rows), inside)


# ------------------------------------------------- the normal equations

def test_the_moments_fit_is_the_measurement_recipe_and_it_adds(world):
    """`fit_from_moments` IS `fit_discriminant`, and moments sum.

    The sufficient statistics carry mean, sd, the ridge system, the
    right-hand side and the class-mean threshold, so a fit read off them
    is the same fit; and because they ADD over disjoint row sets, the
    cross-fit's third filter (A u B) is an addition instead of a third
    normal-equation build.
    """
    rng = np.random.default_rng(11)
    X = rng.random((400, 24))
    y = (X[:, 0] + 0.4 * rng.standard_normal(400) > 0.5).astype(np.uint8)
    direct = autoknobs.fit_discriminant(X, y, shrinkage=1e-2)
    moments = autoknobs.fit_from_moments(autoknobs.moments_of(X, y),
                                         shrinkage=1e-2)
    assert np.allclose(direct.w, moments.w, atol=1e-8, rtol=1e-6)
    assert np.isclose(direct.threshold, moments.threshold, atol=1e-8)
    assert (direct.n_0, direct.n_1) == (moments.n_0, moments.n_1)
    half = np.arange(400) % 2 == 0
    summed = (autoknobs.moments_of(X[half], y[half])
              + autoknobs.moments_of(X[~half], y[~half]))
    whole = autoknobs.moments_of(X, y)
    assert np.allclose(summed.gram, whole.gram, atol=1e-9)
    assert np.allclose(summed.s1, whole.s1, atol=1e-9)
    assert (summed.n, summed.n_1) == (whole.n, whole.n_1)
    # ... and a feature subset is a submatrix, not a refit
    columns = np.arange(5, 17)
    assert np.allclose(whole.select(columns).gram,
                       autoknobs.moments_of(X[:, columns], y).gram,
                       atol=1e-9)


def test_shuffled_labels_leave_the_moments_fit_at_chance(world):
    """The permutation control, on the B8 arithmetic path."""
    rng = np.random.default_rng(3)
    X = rng.random((400, 24))
    y = (X[:, 0] > 0.5).astype(np.uint8)
    honest = autoknobs.fit_from_moments(autoknobs.moments_of(X, y),
                                        shrinkage=1e-2)
    shuffled = autoknobs.fit_from_moments(
        autoknobs.moments_of(X, y[rng.permutation(400)]), shrinkage=1e-2)
    def separation(fit):
        s = autoknobs.apply_discriminant(X, fit)
        return abs(s[y == 1].mean() - s[y == 0].mean()) / max(s.std(), 1e-12)
    assert separation(honest) > 1.5
    assert separation(shuffled) < 0.25


# ------------------------------------------------------------ A7, the crop

def test_refiltering_at_the_crops_own_aperture_is_the_read_itself(world):
    same = sample.refiltered_values(
        world.crops, world.lfp, world.read,
        aperture_cells=float(world.crops.aperture_cells))
    assert np.array_equal(same, world.read.values_rgb, equal_nan=True)
    wider = sample.refiltered_values(world.crops, world.lfp, world.read,
                                     aperture_cells=1.0)
    assert wider.shape == world.read.values_rgb.shape
    assert np.isfinite(wider).all()
    assert not np.array_equal(wider, world.read.values_rgb)
    # a wider box is a smoother read: less spread cell to cell
    assert float(np.std(wider[:, 0])) < float(
        np.std(world.read.values_rgb[:, 0]))
    plain = sample.open_crops(world.lane, world.lfp, bound_dots=2.5,
                              cell_dots=CELL_DOTS, keep_raw=False)
    with pytest.raises(sample.SampleError):
        sample.refiltered_values(plain, world.lfp, world.read,
                                 aperture_cells=1.0)


def test_choose_aperture_keeps_production_on_a_page_printed_for_it(world):
    chosen, values, losses, detail = autoknobs.choose_aperture(
        world.crops, world.lfp, world.read, world.frame, 0, world.mix,
        world.folds, usable=np.asarray(world.lfp.observed, bool))
    assert chosen == float(anchor.APERTURE_CELLS)
    assert values is world.read.values_rgb or np.array_equal(
        values, world.read.values_rgb, equal_nan=True)
    assert detail["refused"] is None
    assert set(losses) == {"inherited", "aperture_cells=0.5",
                           "aperture_cells=1"}
    assert losses["inherited"] < losses["aperture_cells=0.5"]
    assert losses["inherited"] < losses["aperture_cells=1"]


# ---------------------------------------------------------------- blindness

#: The imports no module of the walk may carry: the two that dispatch
#: INTO it (a cycle) and the three offline lanes (DESIGN §0).  Pinned as
#: a DISJOINTNESS since 2026-09-20 — an exact import set made a lawful
#: new import read as a broken no-cycle claim.
_FORBIDDEN_IMPORTS = {"patch", "autoknobs", "truth", "oracle", "score"}


def test_autoknobs_closes_no_cycle_and_reaches_no_truth():
    source = pathlib.Path(autoknobs.__file__).read_text()
    tree = ast.parse(source)
    relative: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            if node.module:                       # from .x import y
                relative.add(str(node.module))
            else:                                 # from . import x as y
                relative.update(alias.name for alias in node.names)
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("analyzer."), alias.name
    assert relative & _FORBIDDEN_IMPORTS == set(), sorted(relative)


def test_patchcache_is_blind_and_closes_no_cycle():
    """W8 B8's economy layer sees pixels and shapes, and nothing else.

    It may not reach `analyzer.autoknobs` or `analyzer.patch` (both
    dispatch into it) and it may not reach truth, the oracle or the
    scorer at any depth — the package-wide closure test pins the second
    half; this pins the first, so the cycle cannot be closed by accident.
    """
    source = pathlib.Path(patchcache.__file__).read_text()
    tree = ast.parse(source)
    relative: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            if node.module:
                relative.add(str(node.module))
            else:
                relative.update(alias.name for alias in node.names)
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("analyzer."), alias.name
    assert relative & _FORBIDDEN_IMPORTS == set(), sorted(relative)

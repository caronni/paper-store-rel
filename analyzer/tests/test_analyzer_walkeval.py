"""HALO-CHANNEL-2026-09-07 — the walk's objective, franchise and burden.

Everything here is synthetic, deterministic and fast.  What it pins:

* the NULL PROOF — with the three walk knobs off and the shrinkage
  NAMED, `patch_score` is the pre-change path to the bit, and
  `autoknobs.paired_verdict` is the arithmetic it always was;
* BLINDNESS — `walkeval` reaches neither `patch` nor `arms`, and the
  cargo profile does not move when the target tile's own cargo bits are
  flipped (they carry no label by construction: `frame`'s run-abort
  assertion is the condition, this is the consequence);
* the three mechanisms, one at a time — W1's covariate recovery and its
  variance budget, W2's franchise (`own` / `pooled` / `inherited`), W3's
  direction on the nested channel axis;
* W4's nesting — a candidate is scored at the argmin over its own ridge
  ladder, and the underdetermined rung appears only when it is;
* the two controls the ruling asks for: a stimulus where the richer
  candidate is genuinely better and the OLD bar refused it, and a
  permutation control where the shuffled labels leave the objective at
  chance;
* fold discipline (the walk counts SEARCH-fold labels and no others),
  determinism, and the CLI's per-plane halo with its own provenance.
"""

from __future__ import annotations

import ast
import pathlib

import numpy as np
import pytest

from analyzer import (autoknobs, calibrate as cal, frame as frame_mod,
                      patch as patch_mod, patchwalk, walkeval)
from analyzer.tests._patch_world import World

#: The three walk knobs at the values that reproduce the OLD walk.  Two
#: of them now SHIP on (§5's isolation flipped them), so the null proof
#: names all three rather than relying on a default.
WALK_OFF: dict = {"walk_weighting": "none", "walk_franchise": "inherit",
                  "walk_direction": "adopt-if-better"}

#: Every filter axis auto EXCEPT the regulariser, which the null proof
#: NAMES: W4 moved the ridge from the end of the coordinate pass to an
#: inner minimisation under every candidate, so a run that leaves it
#: `"auto"` is deliberately not the old path (§4.4's note).
AUTO_NAMED_SHRINKAGE: dict = {
    "patch_samples_per_cell": "auto", "patch_window_cells": "auto",
    "patch_channels": "auto", "patch_features": "auto",
    "patch_min_labels_per_state": "auto",
    "patch_min_labels_agnostic": "auto", "patch_shrinkage": 0.01,
    **WALK_OFF}

#: THE PRE-CHANGE PATH, recorded off `a75c8c1` before a line of this
#: build landed (the `World` fixture, plane C, one call).  Two specs: the
#: auto walk with the ridge named, and the fully named spec.  The scalars
#: are that machine 4 recording, `_sha256_m4` included; the score-array shape
#: statistics under each `sum` were recorded on machine 1 2026-09-20 when
#: the digest stopped being asserted (the null proof's docstring says
#: why), and nothing asserts `_sha256_m4` — it is the provenance.
NULL_FIXTURE: dict = {
    "auto_named_shrinkage": {
        "_sha256_m4":
            "6ee08df2e11ba0ffe2c5c441424e290f85d5e2794752f78b691c6b06"
            "e417a228",
        "sum": 213.2885373654219,
        "shape": (9216,), "nan_cells": 0,
        "sum_of_squares": 9125.131865646625,
        "max": 2.3253519259862396, "argmax": 6399,
        "min": -2.125631904236507, "argmin": 6729,
        "index_weighted_sum": 1021512.7983816238,
        "fit_error_crossfit": 0.005983246908655764,
        "fit_error_insample": 0.0,
        "agnostic_cells": 0, "fallback_cells": 122,
        "fitted_states": (0, 1, 3),
        "auto_choices": {
            "state0": {"samples_per_cell": 8, "window_cells": 1.5,
                       "channels": (0,), "features": "pixels"},
            "state1": {"samples_per_cell": 8, "window_cells": 1.0,
                       "channels": (0,), "features": "pixels"},
            "state3": {"samples_per_cell": 8, "window_cells": 2.0,
                       "channels": (0,), "features": "pixels"},
            "agnostic": {"samples_per_cell": 8, "window_cells": 2.0,
                         "channels": (0,), "features": "pixels"}},
        "auto_losses_state3": {
            "inherited": 0.03706637043554124,
            "samples_per_cell=16": 0.03706637043554124,
            "window_cells=1": 0.05130641162988052,
            "window_cells=2": 0.01847281311378182,
            "channels=012": 0.0517873616760261,
            "features=rings": 0.06174714775917701},
        "n_features": {0: 144, 1: 64, 3: 256}},
    "named": {
        "_sha256_m4":
            "714cfefda9d302839136f5b8817ea30fa2ce39c07a701a472b4ea"
            "a95486b0f48",
        "sum": 129.2275490659975,
        "shape": (9216,), "nan_cells": 0,
        "sum_of_squares": 9140.601520044846,
        "max": 2.448811778586587, "argmax": 5827,
        "min": -2.1178796138554112, "argmin": 8666,
        "index_weighted_sum": 636535.97575941251,
        "fit_error_crossfit": 0.005098039215686275,
        "fit_error_insample": 0.000784313725490196,
        "agnostic_cells": 122, "fallback_cells": 0,
        "fitted_states": (0, 1, 3),
        "auto_choices": {}, "auto_losses_state3": None,
        "n_features": {0: 144, 1: 144, 3: 144}},
}


def _assert_score_is_the_recorded_run(score: np.ndarray, want: dict) -> None:
    array = np.ascontiguousarray(score)
    assert array.shape == want["shape"]
    assert int(np.isnan(array).sum()) == want["nan_cells"]
    assert float(np.nansum(array)) == pytest.approx(want["sum"], abs=1e-9)
    assert float(np.nansum(array * array)) == pytest.approx(
        want["sum_of_squares"], abs=1e-9)
    assert float(np.nanmax(array)) == pytest.approx(want["max"], abs=1e-9)
    assert int(np.nanargmax(array)) == want["argmax"]
    assert float(np.nanmin(array)) == pytest.approx(want["min"], abs=1e-9)
    assert int(np.nanargmin(array)) == want["argmin"]
    # order-sensitive, so a permuted array cannot pass on the moments alone
    weights = np.arange(array.size, dtype=np.float64)
    assert float(np.nansum(array * weights)) == pytest.approx(
        want["index_weighted_sum"], abs=1e-6)


# ------------------------------------------------------------ null proof

@pytest.mark.parametrize("name,knobs",
                         [("auto_named_shrinkage", AUTO_NAMED_SHRINKAGE),
                          ("named", dict(WALK_OFF))])
def test_the_walk_knobs_off_reproduce_the_pre_change_path_exactly(
        world: World, name: str, knobs: dict):
    """The NULL PROOF (§4.7): score AND detail, against a recorded run.

    New KEYS in the detail are allowed — `auto_source`, `auto_verdicts`
    and `labels_per_feature_chosen` are the point of the build — but no
    value the old path published may move.  The score was the sha256 of
    its bytes until 2026-09-20; machine 4 recording and machine 1 disagree
    there while the sum moves 1.3e-12 on 213.29 and 5.2e-12 on 129.23,
    every other scalar is bit-exact and `a75c8c1` replayed on machine 1
    gives this build's values bit for bit — a reduction-order difference
    between two interpreters, not a regression — so the score is pinned
    instead by shape, NaN count, sum, sum of squares and the two extremes
    with their positions, floats to 1e-9 absolute: a single cell moving
    by 1e-9 shows up in the sum, a compensating pair in the squares, a
    shifted array in both, and a reordering at the extremes (a swap of
    two interior cells is the one thing this lets through, measured).
    Machine 4 digest stays in the fixture, asserted by nothing.
    """
    want = NULL_FIXTURE[name]
    score, detail = world.score(patch_mod.spec_from_knobs(knobs))
    _assert_score_is_the_recorded_run(score, want)
    assert detail["patch_fit_error_crossfit"] == want["fit_error_crossfit"]
    assert detail["patch_fit_error_insample"] == want["fit_error_insample"]
    assert detail["patch_agnostic_cells"] == want["agnostic_cells"]
    assert detail["patch_fallback_cells"] == want["fallback_cells"]
    assert detail["patch_fitted_states"] == want["fitted_states"]
    assert {tag: dict(choice)
            for tag, choice in detail["auto_choices"].items()} == \
        want["auto_choices"]
    if want["auto_losses_state3"] is not None:
        assert detail["auto_losses"]["state3"] == want["auto_losses_state3"]
    for state, features in want["n_features"].items():
        assert detail["patch_states"][state]["n_features"] == features
    # the three knobs are OFF and the detail says so
    assert detail["patch_walk_weighting"] == "none"
    assert detail["patch_walk_franchise"] == "inherit"
    assert detail["patch_walk_direction"] == "adopt-if-better"
    assert detail["patch_walk_cargo_cells"] is None
    # ... and W4's inner axis is not engaged when the ridge is NAMED
    assert detail["patch_walk_inner_axis"] is None


def test_the_plain_paired_verdict_is_the_arithmetic_it_always_was():
    """`autoknobs.paired_verdict` is a thin call and moves nothing."""
    rng = np.random.default_rng(5)
    base = rng.random(200) + 0.5
    for candidate in (base.copy(), base - 0.4, base + 0.4,
                      base + rng.normal(0.0, 1.0, 200)):
        got = autoknobs.paired_verdict(base, candidate)
        difference = base - candidate
        assert got["mean_difference"] == float(np.mean(difference))
        assert got["standard_error"] == float(
            np.std(difference, ddof=1) / np.sqrt(difference.size))
        assert got["select_logloss"] == float(np.mean(candidate))
        assert got["adopted"] is bool(
            got["mean_difference"] > cal.SELECT_SE_MULTIPLE
            * got["standard_error"] and got["standard_error"] > 0.0)
    short = autoknobs.paired_verdict(base[:5], base[:5] - 0.4)
    assert short["adopted"] is False
    assert short["reason"] == "too_few_paired_labels"
    # ... and the weighted form with unit weights agrees with it
    unit = walkeval.paired_verdict(base, base - 0.01,
                                   weights=np.ones(base.size))
    plain = autoknobs.paired_verdict(base, base - 0.01)
    assert unit["mean_difference"] == pytest.approx(
        plain["mean_difference"], abs=1e-12)
    assert unit["standard_error"] == pytest.approx(
        plain["standard_error"], rel=1e-12)


# ------------------------------------------------------------- blindness

def _relative_imports(module) -> set[str]:
    tree = ast.parse(pathlib.Path(module.__file__).read_text("utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            if node.module:
                out.add(str(node.module))
            else:
                out.update(alias.name for alias in node.names)
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("analyzer."), alias.name
    return out


def test_walkeval_reaches_neither_patch_nor_arms_nor_the_offline_lanes():
    """The cycle and the blindness, both pinned at the import level.

    `walkeval` may not import `patch`, `autoknobs`, `arms` or `unmix`
    (the first two dispatch into it), and its ONE deferred import —
    `patchfit`, which imports `autoknobs`, which imports this module —
    is the named exception in the docstring.  The package-wide closure
    test (`test_analyzer_fixedpoint`) picks the module up on its own and
    proves it reaches no truth, oracle or scorer at any depth.
    """
    relative = _relative_imports(walkeval)
    assert relative == {"calibrate", "patchfit"}
    for banned in ("patch", "autoknobs", "arms", "unmix", "truth", "oracle",
                   "score"):
        assert banned not in relative


def test_patchwalk_is_blind_and_dispatches_only_downward():
    relative = _relative_imports(patchwalk)
    assert relative == {"autoknobs", "patchcache", "walkeval", "patchgrid"}
    for banned in ("patch", "arms", "unmix", "truth", "oracle", "score"):
        assert banned not in relative
    #: the two knob VALUES `patchwalk` spells for itself rather than
    #: importing the module that builds the spec
    from analyzer import patchspec
    assert patchwalk._NESTED == patchspec.WALK_DIRECTION_NESTED
    assert patchwalk._POOLED == patchspec.WALK_FRANCHISE_POOLED


def test_the_cargo_profile_reads_no_label_of_the_target_plane(world: World):
    """§4.5's assertion is the condition; this is the consequence.

    The target tile's cargo carries NO target-plane bit (`frame` aborts a
    run where it does), so a profile built over those cells is a
    histogram of an UNLABELLED population: flip every one of those bits
    and the profile must not move by a float.
    """
    frame = world.frame
    plane = 0
    fallback = world.box_score()
    in_tile = np.asarray(world.fp.in_tile, bool)
    cargo = np.asarray(world.fp.cargo, bool)
    known_target = np.asarray(frame.known[:, plane], bool)
    values = np.asarray(frame.bits[:, plane], np.uint8)
    assert not np.any(known_target & in_tile & cargo), "the §4.5 condition"
    state = np.zeros(values.size, np.int8)
    state[:] = (frame.bits[:, 1].astype(np.int8)
                + 2 * frame.bits[:, 2].astype(np.int8))
    observed = np.asarray(world.lfp.observed, bool)
    kwargs = dict(observed=observed, in_tile=in_tile, cargo=cargo,
                  state=state, known_target_fit=known_target & world.folds.fit,
                  min_per_class=8, n_walk_labels=400)
    first = walkeval.cargo_profile(fallback, values=values, **kwargs)
    flipped = values.copy()
    flipped[in_tile & cargo] ^= 1
    second = walkeval.cargo_profile(fallback, values=flipped, **kwargs)
    assert first.centre == second.centre and first.scale == second.scale
    assert first.n_cargo_by_state == second.n_cargo_by_state
    assert set(first.edges) == set(second.edges)
    for key, edges in first.edges.items():
        assert np.array_equal(edges, second.edges[key])
        assert np.array_equal(first.bins_by_state[key],
                              second.bins_by_state[key])
    assert first.n_cargo > 0


# ------------------------------------------------- W1, covariate recovery

def _planted(n_easy: int, n_hard: int, easy_loss: float, hard_loss: float):
    """A halo of two difficulty classes with a planted per-label loss."""
    z = np.concatenate((np.full(n_easy, 3.0), np.full(n_hard, 0.1)))
    loss = np.concatenate((np.full(n_easy, easy_loss),
                           np.full(n_hard, hard_loss)))
    return z, loss


#: eight labelled fit rows per class at -1 and +1, appended to every
#: synthetic page: they put `fallback_population`'s class midpoint at 0
#: and its scale at 1, so `z` IS the score the test hands in and the
#: covariate under test is not confounded with the standardisation.
_ANCHOR_SCORES = np.concatenate((np.full(8, -1.0), np.full(8, 1.0)))
_ANCHOR_BITS = np.concatenate((np.zeros(8, np.uint8), np.ones(8, np.uint8)))


def _profile_over(halo_z: np.ndarray, cargo_z: np.ndarray, *,
                  n_walk_labels: int = 400):
    """A profile whose halo rows come first and whose cargo comes second."""
    n, m = halo_z.size, cargo_z.size
    total = n + m + _ANCHOR_SCORES.size
    in_tile = np.zeros(total, bool)
    in_tile[n:n + m] = True
    known_fit = np.zeros(total, bool)
    known_fit[n + m:] = True
    values = np.zeros(total, np.uint8)
    values[n + m:] = _ANCHOR_BITS
    profile = walkeval.cargo_profile(
        np.concatenate((halo_z, cargo_z, _ANCHOR_SCORES)),
        observed=np.ones(total, bool), in_tile=in_tile,
        cargo=in_tile.copy(), state=np.zeros(total, np.int8),
        known_target_fit=known_fit, values=values, min_per_class=8,
        n_walk_labels=n_walk_labels)
    assert profile.centred_on == "class_midpoint"
    assert profile.centre == pytest.approx(0.0) and profile.scale == \
        pytest.approx(1.0)
    return profile, np.zeros(n, np.int8), profile.z[:n]


def test_the_weighting_recovers_the_cargos_own_mean_inside_its_budget():
    """W1's covariate recovery, and the budget that bounds it.

    A halo 60/40 easy/hard against a cargo 40/60: the weighted mean of a
    planted per-label loss equals the CARGO-weighted mean to 1e-9 — that
    is what the weighting is for — and the effective sample size still
    clears half the raw count.

    DEVIATION FROM §4.7's WORDING, recorded: the ruling's own stimulus
    (80/20 against 20/80) asks for both, and it cannot have both.  That
    mismatch needs a raw weight ratio of 16, whose Kish ESS is 154 of
    500 — under the floor — so the clip engages and the recovery becomes
    partial BY CONSTRUCTION.  The second half of this test is that case,
    and what it pins is the budget: the correction may not spend more
    than the effect it corrects (§4.1).
    """
    halo = np.concatenate((np.full(300, 3.0), np.full(200, 0.1)))
    cargo = np.concatenate((np.full(200, 3.0), np.full(300, 0.1)))
    loss = np.concatenate((np.full(300, 0.02), np.full(200, 0.30)))
    profile, state, z = _profile_over(halo, cargo)
    assert profile.n_bins == 4
    weights, detail = walkeval.cargo_weights(profile, state_of_row=state,
                                             z_of_row=z, pooled=False)
    assert weights is not None and detail["refused"] is None
    want = float(np.mean(np.where(cargo > 1.0, 0.02, 0.30)))
    got = float(np.sum(weights * loss) / np.sum(weights))
    assert got == pytest.approx(want, abs=1e-9)
    assert detail["ess"] >= walkeval.ESS_FLOOR_FRACTION * halo.size
    assert detail["clip"] is None                  # no clipping needed
    assert detail["unmatched_cargo_fraction"] == pytest.approx(0.0)

    # ... and the 80/20 against 20/80 case, where the budget binds
    halo = np.concatenate((np.full(400, 3.0), np.full(100, 0.1)))
    cargo = np.concatenate((np.full(100, 3.0), np.full(400, 0.1)))
    loss = np.concatenate((np.full(400, 0.02), np.full(100, 0.30)))
    profile, state, z = _profile_over(halo, cargo)
    weights, detail = walkeval.cargo_weights(profile, state_of_row=state,
                                             z_of_row=z, pooled=False)
    assert weights is not None and detail["clip"] is not None
    assert detail["ess"] == pytest.approx(
        walkeval.ESS_FLOOR_FRACTION * halo.size, rel=1e-6)
    plain = float(np.mean(loss))
    clipped = float(np.sum(weights * loss) / np.sum(weights))
    target = float(np.mean(np.where(cargo > 1.0, 0.02, 0.30)))
    assert plain < clipped < target, "toward the cargo, inside the budget"


def test_the_bin_count_is_affordable_for_the_walk_that_gets_the_fewest():
    """§4.1's own derivation, applied to the population that pays it.

    The profile is built ONCE per `patch_score` call from the TILE-WIDE
    search-fold count, and it serves the per-state walks, which see
    roughly their own state's share of that count.  Deriving four bins
    from the tile-wide number gave a per-state walk four bins on a
    quarter of the labels — the regime the derivation says cannot carry
    a paired difference (2026-09-07 review).
    """
    assert walkeval.WALK_POPULATIONS == 4
    halo, _loss = _planted(300, 200, 0.02, 0.30)
    cargo, _ = _planted(200, 300, 0.02, 0.30)
    for labels, want in ((400, 4), (451, 4), (300, 3), (200, 2),
                         (100, 1), (40, 1)):
        profile, _state, _z = _profile_over(halo, cargo,
                                            n_walk_labels=labels)
        assert profile.n_bins == want, labels
        #: every bin still carries the floor at the population that
        #: actually walks it
        assert (labels // walkeval.WALK_POPULATIONS) >= (
            want * walkeval.MIN_LABELS_PER_BIN) or want == 1


def test_the_weights_reach_the_inner_ridge_and_the_published_loss():
    """W1 weights the DECISION, so it must weight what the decision reads.

    2026-09-07 review: `choose`'s inner minimisation picked each
    candidate's ridge by the plain halo mean while the outer paired
    verdict used the weights, so under `walk_weighting=cargo` the
    regulariser was chosen on exactly the population W1 exists to
    reject, and `auto_losses` / `baseline_logloss` named neither.
    """
    #: half the labels are the cargo's kind (weight 3), half are not
    #: (weight 1/3); the plain mean prefers ridge A, the cargo-weighted
    #: mean prefers ridge B
    hard = np.zeros(40, bool)
    hard[:20] = True
    weights = np.where(hard, 3.0, 1.0 / 3.0)
    ridge_a = np.where(hard, 0.40, 0.05)          # plain 0.225
    ridge_b = np.where(hard, 0.20, 0.30)          # plain 0.250
    table = {(1e-2,): ridge_a, (1e-3,): ridge_b, (1e-1,): ridge_a}

    def evaluate(axes):
        return table[(float(axes["shrinkage"]),)]

    plain = float(np.mean(ridge_a)) < float(np.mean(ridge_b))
    assert plain, "the plain mean prefers A"
    got_a = float(np.sum(weights * ridge_a) / np.sum(weights))
    got_b = float(np.sum(weights * ridge_b) / np.sum(weights))
    assert got_b < got_a, "the cargo-weighted mean prefers B"
    axes, losses, detail = autoknobs.choose(
        {"shrinkage": 1e-2}, {}, evaluate, order=(),
        inner_axis="shrinkage",
        inner_candidates=autoknobs.SHRINKAGE_CANDIDATES)
    assert axes["shrinkage"] == 1e-2               # unweighted: A
    assert losses["inherited"] == pytest.approx(float(np.mean(ridge_a)))
    assert detail["loss_population"] == walkeval.LOSS_HALO
    axes, losses, detail = autoknobs.choose(
        {"shrinkage": 1e-2}, {}, evaluate, order=(), weights=weights,
        inner_axis="shrinkage",
        inner_candidates=autoknobs.SHRINKAGE_CANDIDATES)
    assert axes["shrinkage"] == 1e-3               # weighted: B
    assert losses["inherited"] == pytest.approx(got_b)
    assert detail["baseline_logloss"] == pytest.approx(got_b)
    assert detail["loss_population"] == walkeval.LOSS_CARGO
    #: and the helper is `np.mean` to the bit with no weights
    assert walkeval.weighted_mean(ridge_a, None) == float(np.mean(ridge_a))
    assert walkeval.loss_population(None) == walkeval.LOSS_HALO


def test_the_variance_budget_clips_and_refuses_rather_than_pretend():
    """The clip is the LEAST that fits the budget; below it, a refusal."""
    raw = np.concatenate((np.full(99, 0.01), np.array([100.0])))
    clipped, clip, ess = walkeval._clip_to_budget(raw, 0.5 * raw.size)
    assert clipped is None and clip is None      # cannot reach n/2 at all
    gentle = np.concatenate((np.full(90, 1.0), np.full(10, 3.0)))
    kept, clip, ess = walkeval._clip_to_budget(gentle, 0.5 * gentle.size)
    assert clip is None and ess >= 0.5 * gentle.size
    assert np.array_equal(kept, gentle)          # no clipping needed
    steep = np.concatenate((np.full(95, 0.2), np.full(5, 16.2)))
    kept, clip, ess = walkeval._clip_to_budget(steep, 0.5 * steep.size)
    assert kept is not None and clip is not None and clip > 1.0
    assert ess >= 0.5 * steep.size
    assert walkeval._ess(steep) < 0.5 * steep.size
    # monotone: a bigger cap lets the extremes back in
    assert (walkeval._ess(np.minimum(steep, clip))
            >= walkeval._ess(np.minimum(steep, clip * 1.5)))


def test_unmatchable_cargo_refuses_the_weighting_and_the_walk_runs_plain():
    """Cargo mass in bins holding no halo label: a refusal, never a lie."""
    halo = np.full(200, 5.0)                     # every halo label EASY
    cargo = np.full(200, 0.01)                   # every cargo cell HARD
    profile, state, z = _profile_over(halo, cargo)
    weights, detail = walkeval.cargo_weights(profile, state_of_row=state,
                                             z_of_row=z, pooled=False)
    assert weights is None
    assert detail["refused"] == "cargo_mass_the_halo_cannot_reach"
    assert detail["unmatched_cargo_fraction"] > walkeval.MAX_UNMATCHED_CARGO
    #: a walk handed no weights is the unweighted walk, not a broken one
    assert autoknobs.choose(
        {"channels": (0,)}, {"channels": autoknobs.CHANNEL_CANDIDATES},
        _table_evaluate({_key(channels=(0,)): 0.3,
                         _key(channels=(0, 1, 2)): 0.1}),
        order=("channels",), weights=None)[0]["channels"] == (0, 1, 2)


# ------------------------------------------------------- W2, the franchise

def _walk_context(**over) -> patchwalk.WalkContext:
    n = 60
    base = dict(
        spec=patch_mod.PatchSpec(), bank=None,
        inherited_axes={"samples_per_cell": 8, "window_cells": 1.5,
                        "channels": (0,), "features": "pixels",
                        "shrinkage": 1e-2},
        axis_names=("channels",), walk_order=("channels",), inner_axis=None,
        known_target=np.ones(n, bool), observed=np.ones(n, bool),
        inside=np.ones(n, bool), word=np.zeros(n, bool),
        search=np.ones(n, bool), values=np.zeros(n, np.uint8),
        state=np.zeros(n, np.int8), half=np.zeros(n, bool),
        sel_index=np.arange(n, dtype=np.int64),
        agnostic_rows=np.arange(n, dtype=np.int64), pitch_px=8.0, n=n)
    base.update(over)
    return patchwalk.WalkContext(**base)


#: what a successful pooled walk looks like, pre-seeded into the memo
_POOLED_RGB = ({"samples_per_cell": 8, "window_cells": 1.5,
                "channels": (0, 1, 2), "features": "pixels",
                "shrinkage": 1e-2},
               {"inherited": 0.31, "channels=012": 0.20},
               {"refused": None, "adopted": {"channels": "channels=012"},
                "n_walk_labels": 900})


def test_a_population_that_cannot_vote_inherits_a_discovery_not_a_pin():
    """W2.  Below `SELECT_MIN_MINORITY` the walk used to return the module
    constants and `_record_auto` wrote them down as if they were a
    choice — 674 of 3,186 three-ink populations at halo 16."""
    rows = np.arange(60, dtype=np.int64)
    mine = np.ones(60, bool)
    # with the franchise NAMED off the pin stands, and says so
    ctx = _walk_context(
        spec=patch_mod.PatchSpec(walk_franchise="inherit"),
        pooled=[_POOLED_RGB])
    axes, losses, detail, source = patchwalk.choose_axes(
        ctx, mine, rows, tag="state3", exclude_word=False)
    assert source == "inherited" and axes["channels"] == (0,)
    assert detail["refused"] == "below_minority_floor" and losses == {}
    # ... and under `pooled` it takes the POOLED walk's discovery
    ctx = _walk_context(pooled=[_POOLED_RGB])       # the shipped franchise
    axes, losses, detail, source = patchwalk.choose_axes(
        ctx, mine, rows, tag="state3", exclude_word=False)
    assert source == "pooled" and axes["channels"] == (0, 1, 2)
    assert detail["refused"] == "below_minority_floor"
    assert detail["pooled_adopted"] == {"channels": "channels=012"}
    #: the pooled walk's LOSSES stay under its own tag, once
    assert losses == {}
    # ... and when the pooled walk ALSO refuses, the constants stand
    refused = (dict(_POOLED_RGB[0]), {}, {"refused": "below_minority_floor"})
    ctx = _walk_context(pooled=[refused])
    axes, _losses, detail, source = patchwalk.choose_axes(
        ctx, mine, rows, tag="state3", exclude_word=False)
    assert source == "inherited" and axes["channels"] == (0,)
    assert detail["pooled_refused"] == "below_minority_floor"


def test_the_pooled_walk_is_computed_at_most_once(monkeypatch):
    """W2 must not walk twice: the tier at step 6 reuses the memo."""
    calls: list[str] = []

    def fake(ctx, mine, rows_train, *, tag, exclude_word):
        calls.append(tag)
        return _POOLED_RGB

    monkeypatch.setattr(patchwalk, "own_axes", fake)
    ctx = _walk_context()
    first = patchwalk.pooled_axes(ctx)
    second = patchwalk.pooled_axes(ctx)
    assert first is second and calls == [patchwalk.POOLED_TAG]


def test_the_ledger_separates_a_vote_from_an_inheritance():
    ledger = patchwalk.AutoLedger()
    ledger.record("state3", _POOLED_RGB[0], {}, {
        "refused": "below_minority_floor",
        "verdicts": {"channels=012": {"mean_difference": 0.01,
                                      "standard_error": 0.02, "ess": 90.0,
                                      "n": 100, "adopted": False}},
        "walk_weights": {"ess": 90.0, "n_bins": 4,
                         "unmatched_cargo_fraction": 0.1, "refused": None}},
        "pooled", ("channels",))
    assert ledger.choices["state3"] == {"channels": (0, 1, 2)}
    assert ledger.refused["state3"] == "below_minority_floor"
    assert ledger.detail["state3"]["auto_source"] == "pooled"
    assert ledger.detail["state3"]["walk_ess"] == 90.0
    assert ledger.verdicts["state3"]["channels=012"]["adopted"] is False
    # nothing auto: nothing recorded, which is what a named run reads
    empty = patchwalk.AutoLedger()
    empty.record("state3", _POOLED_RGB[0], {}, {}, "inherited", ())
    assert not empty.choices and not empty.detail


# -------------------------------------------------------- W3, the direction

def _table_evaluate(table, default=0.5, spread=1e-9, size=200):
    """An `evaluate` whose per-label losses depend only on its axes."""
    def evaluate(axes):
        key = tuple(sorted((name, tuple(value)
                            if isinstance(value, (tuple, list)) else value)
                           for name, value in axes.items()))
        mean = table.get(key, default)
        if mean is None:
            return None
        step = np.linspace(-1.0, 1.0, size)
        return np.full(size, mean) + spread * step
    return evaluate


def _key(**axes):
    return tuple(sorted((name, tuple(value)
                         if isinstance(value, (tuple, list)) else value)
                        for name, value in axes.items()))


def test_a_nested_axis_adopts_the_richer_candidate_on_a_tie():
    inherited = {"channels": (0,)}
    evaluate = _table_evaluate({_key(channels=(0,)): 0.30,
                                _key(channels=(0, 1, 2)): 0.30})
    axes, losses, detail = autoknobs.choose(
        inherited, {"channels": autoknobs.CHANNEL_CANDIDATES}, evaluate,
        order=("channels",))
    assert axes["channels"] == (0,), "ties lose without the nesting"
    axes, losses, detail = autoknobs.choose(
        inherited, {"channels": autoknobs.CHANNEL_CANDIDATES}, evaluate,
        order=("channels",),
        nested={"channels": autoknobs.CHANNEL_CANDIDATES})
    assert axes["channels"] == (0, 1, 2)
    assert detail["adopted"] == {"channels": "channels=012"}
    assert detail["verdicts"]["channels=012"]["adopted"] is True


def test_a_nested_axis_refuses_the_richer_candidate_that_reads_worse():
    """A planted 3-SE advantage for the LEANER side holds the rung."""
    rng = np.random.default_rng(11)
    lean = rng.normal(0.30, 0.05, 400)
    size = lean.size
    gap = 3.0 * float(np.std(lean, ddof=1) / np.sqrt(size))
    rich = lean + gap * 1.5

    def evaluate(axes):
        return rich if tuple(axes["channels"]) == (0, 1, 2) else lean

    axes, _losses, detail = autoknobs.choose(
        {"channels": (0,)}, {"channels": autoknobs.CHANNEL_CANDIDATES},
        evaluate, order=("channels",),
        nested={"channels": autoknobs.CHANNEL_CANDIDATES})
    assert axes["channels"] == (0,)
    assert detail["verdicts"]["channels=012"]["adopted"] is False


def test_a_constant_difference_is_read_by_its_sign_in_both_directions():
    """The degenerate paired difference (2026-09-07 review).

    With a zero-variance difference the bar is 0 and the old
    `se > 0.0` conjunct made it unreachable, so under `DIRECTION_KEEP`
    a richer candidate that was uniformly and DETERMINISTICALLY worse
    was adopted.  A constant difference needs no standard error to be
    read: its sign is the whole evidence.  Ties still go to the richer
    model, which is what the direction is for.
    """
    flat = np.full(40, 0.10)
    worse = np.full(40, 0.90)
    better = np.full(40, 0.01)
    kept = walkeval.paired_verdict(flat, worse,
                                   direction=walkeval.DIRECTION_KEEP)
    assert kept["standard_error"] == 0.0 and kept["mean_difference"] < 0.0
    assert kept["adopted"] is False
    tie = walkeval.paired_verdict(flat, flat.copy(),
                                  direction=walkeval.DIRECTION_KEEP)
    assert tie["standard_error"] == 0.0 and tie["adopted"] is True
    gain = walkeval.paired_verdict(flat, better,
                                   direction=walkeval.DIRECTION_KEEP)
    assert gain["adopted"] is True
    #: DIRECTION_ADOPT stays conservative at exactly zero variance — a
    #: candidate still has to clear a bar, and nothing measured asks for
    #: that to change
    assert walkeval.paired_verdict(flat, better)["adopted"] is False
    #: and the nested climb refuses the rung, which is what the guard
    #: test above could not reach (its planted offset leaves 1e-17 of
    #: floating-point residue, so it refuses on the ordinary branch)
    def evaluate(axes):
        return worse if tuple(axes["channels"]) == (0, 1, 2) else flat
    axes, losses, _detail = autoknobs.choose(
        {"channels": (0,)}, {"channels": autoknobs.CHANNEL_CANDIDATES},
        evaluate, order=("channels",),
        nested={"channels": autoknobs.CHANNEL_CANDIDATES})
    assert axes["channels"] == (0,)
    assert losses["channels=012"] == pytest.approx(0.90)


def test_the_richer_candidate_wins_a_budget_the_old_bar_refused():
    """The stimulus the ruling is about (§2.3, §3(b) W3).

    `rgb` reads GENUINELY better — the paired mean difference is
    positive — but by less than two standard errors at this label
    budget, which is the 1,033 of 2,512 walked three-ink populations at
    halo 16 that measured `rgb` better and refused it.  The direction
    flip is exactly what changes the answer; the losses do not move.
    """
    rng = np.random.default_rng(3)
    size = 300
    lean = rng.normal(0.30, 0.05, size)
    #: a paired difference with real spread whose MEAN is one standard
    #: error — genuinely better, and inside the 2-SE bar
    difference = rng.normal(0.0, 0.01, size)
    difference = difference - difference.mean()
    difference += float(np.std(difference, ddof=1) / np.sqrt(size))
    rich = lean - difference
    def evaluate(axes):
        return rich if tuple(axes["channels"]) == (0, 1, 2) else lean
    plain = autoknobs.choose({"channels": (0,)},
                             {"channels": autoknobs.CHANNEL_CANDIDATES},
                             evaluate, order=("channels",))
    assert plain[0]["channels"] == (0,)
    assert plain[2]["verdicts"]["channels=012"]["mean_difference"] > 0.0
    assert not plain[2]["verdicts"]["channels=012"]["adopted"]
    nested = autoknobs.choose(
        {"channels": (0,)}, {"channels": autoknobs.CHANNEL_CANDIDATES},
        evaluate, order=("channels",),
        nested={"channels": autoknobs.CHANNEL_CANDIDATES})
    assert nested[0]["channels"] == (0, 1, 2)
    assert nested[1] == plain[1], "the LOSSES are the same measurement"


def test_what_the_richer_tie_break_costs_where_the_channels_are_noise(
        world: World):
    """W3's own price, measured on a stimulus built against it.

    `_patch_world.py`'s synthetic page paints M in green and Y in
    blue, so for a C cell held at ONE sibling state the extra two
    channels carry nothing but the neighbours' ink and capture noise.
    The paired test there reads a TIE, and under `nested-richer` a tie
    goes to the richer model: state 0 takes `rgb` and its held-out d'
    falls by about a tenth.  That is the rule working as ruled, not a
    bug — under-richness cost 13-19 certificates on the matrix that
    argues for it and over-richness cost 0 — and it is recorded here so
    nobody meets it as a surprise.  On a sheet where the extra channels
    are noise AND the paired test can see it, the lean model still wins:
    state 1 and state 3 keep `r` in the same run.
    """
    from analyzer.tests._patch_world import AUTO_KNOBS, d_prime
    lean = patch_mod.spec_from_knobs(AUTO_KNOBS)
    rich = patch_mod.spec_from_knobs({**AUTO_KNOBS,
                                      "walk_direction": "nested-richer"})
    lean_score, lean_detail = world.score(lean)
    rich_score, rich_detail = world.score(rich)
    assert lean_detail["auto_choices"]["state0"]["channels"] == (0,)
    assert rich_detail["auto_choices"]["state0"]["channels"] == (0, 1, 2)
    #: where the paired test SEES the harm, the leaner side still holds
    for state in ("state1", "state3"):
        assert rich_detail["auto_choices"][state]["channels"] == (0,)
    target = world.frame.bits[:, 0] == 1
    rows = world.heldout(0)
    lean_d = d_prime(lean_score[rows], target[rows])
    rich_d = d_prime(rich_score[rows], target[rows])
    box_d = d_prime(world.box_score()[rows], target[rows])
    assert box_d < rich_d < lean_d
    assert rich_d > 0.85 * lean_d


def test_the_non_nested_axes_still_keep_every_tie():
    """W3's scope is deliberately the channel axis and nothing else."""
    evaluate = _table_evaluate({_key(channels=(0,), window_cells=1.5): 0.30,
                                _key(channels=(0,), window_cells=1.0): 0.30,
                                _key(channels=(0,), window_cells=2.0): 0.30,
                                _key(channels=(0, 1, 2),
                                     window_cells=1.5): 0.30,
                                _key(channels=(0, 1, 2),
                                     window_cells=1.0): 0.30,
                                _key(channels=(0, 1, 2),
                                     window_cells=2.0): 0.30})
    axes, _losses, _detail = autoknobs.choose(
        {"channels": (0,), "window_cells": 1.5},
        {"channels": autoknobs.CHANNEL_CANDIDATES,
         "window_cells": autoknobs.WINDOW_CANDIDATES},
        evaluate, order=("window_cells", "channels"),
        nested={"channels": autoknobs.CHANNEL_CANDIDATES})
    assert axes["window_cells"] == 1.5 and axes["channels"] == (0, 1, 2)


# --------------------------------------------------- W4, the nested ridge

def test_every_candidate_is_scored_at_the_argmin_over_its_own_ridge():
    """The channel axis is no longer judged at the INHERITED ridge."""
    table = {_key(channels=(0,), shrinkage=1e-2): 0.30,
             _key(channels=(0,), shrinkage=1e-3): 0.31,
             _key(channels=(0,), shrinkage=1e-1): 0.32,
             _key(channels=(0, 1, 2), shrinkage=1e-2): 0.29,
             _key(channels=(0, 1, 2), shrinkage=1e-3): 0.33,
             #: the richer model asks for MORE ridge, and under W4 it is
             #: allowed to ask BEFORE the vote instead of after it
             _key(channels=(0, 1, 2), shrinkage=1e-1): 0.10}
    axes, losses, detail = autoknobs.choose(
        {"channels": (0,), "shrinkage": 1e-2},
        {"channels": autoknobs.CHANNEL_CANDIDATES}, _table_evaluate(table),
        order=("channels",), inner_axis="shrinkage",
        inner_candidates=autoknobs.SHRINKAGE_CANDIDATES)
    assert axes == {"channels": (0, 1, 2), "shrinkage": 1e-1}
    assert losses["inherited"] == pytest.approx(0.30)
    assert losses["channels=012"] == pytest.approx(0.10)
    assert detail["inner"]["channels=012"] == "shrinkage=0.1"
    # a tie inside the ladder keeps the ridge the population already had
    flat = {_key(channels=(0,), shrinkage=value): 0.30
            for value in autoknobs.SHRINKAGE_CANDIDATES}
    axes, _losses, _detail = autoknobs.choose(
        {"channels": (0,), "shrinkage": 1e-2}, {}, _table_evaluate(flat),
        order=(), inner_axis="shrinkage",
        inner_candidates=autoknobs.SHRINKAGE_CANDIDATES)
    assert axes["shrinkage"] == 1e-2


def test_the_ridge_the_ledger_publishes_is_the_ridge_it_was_fitted_at(
        world: World):
    """The 2026-09-07 review's blocker, pinned end to end.

    W4 minimises the regulariser inside every candidate and publishes
    the winner in `auto_choices`; `patch_score` then fitted the
    population through `fit_population`, which read `spec.shrinkage` —
    the INHERITED constant — so the run paid 1.92x the CPU for a value
    it discarded and the ledger named a ridge no filter was fitted at.
    """
    #: every filter axis auto INCLUDING the ridge, and the walk at its
    #: SHIPPED knobs — the configuration `--profile patch` produces
    knobs = {name: "auto" for name in AUTO_NAMED_SHRINKAGE
             if name.startswith("patch_")}
    spec = patch_mod.spec_from_knobs(knobs)
    assert "shrinkage" in spec.auto
    _score, detail = world.score(spec)
    fitted = {f"state{index}": entry.get("shrinkage_fitted")
              for index, entry in detail["patch_states"].items()
              if entry.get("fitted")}
    fitted["agnostic"] = detail["patch_agnostic"].get("shrinkage_fitted")
    seen = set()
    for tag, ridge in fitted.items():
        if ridge is None:
            continue
        chose = detail["auto_choices"][tag]["shrinkage"]
        assert ridge == pytest.approx(chose), tag
        seen.add(float(ridge))
    assert seen, "no population was fitted at all"
    #: and the walk really does move it: at least one population is
    #: fitted at something OTHER than the spec's inherited constant, so
    #: this test fails on the pre-fix path rather than passing vacuously
    assert seen - {float(spec.shrinkage)}


def test_the_underdetermined_rung_appears_only_when_it_is():
    assert autoknobs.shrinkage_ladder(500, 144) == \
        autoknobs.SHRINKAGE_CANDIDATES
    assert autoknobs.shrinkage_ladder(144, 144) == \
        autoknobs.SHRINKAGE_CANDIDATES
    wider = autoknobs.shrinkage_ladder(143, 144)
    assert wider == autoknobs.SHRINKAGE_CANDIDATES + (
        autoknobs.SHRINKAGE_UNDERDETERMINED_RUNG,)
    assert autoknobs.SHRINKAGE_UNDERDETERMINED_RUNG == 1.0
    assert "shrinkage" not in autoknobs.AXIS_ORDER
    assert autoknobs.WALK_ORDER[-1] == autoknobs.INNER_AXIS


# --------------------------------------------------- the permutation control

def test_shuffled_labels_leave_the_objective_at_chance():
    """The control the ruling asks for.

    With the fit labels shuffled the two candidates carry no signal, so
    the WEIGHTED paired difference between them must sit inside its own
    noise — the weighting may not manufacture a preference for the
    richer model — and the ordinary walk must adopt nothing.  (Under
    `nested-richer` a tie DOES go to the richer model: that is the
    ruling's rule, not an artefact, and it is pinned above.)
    """
    rng = np.random.default_rng(19)
    n = 600
    lean = rng.random(n) * 0.6 + 0.4
    rich = rng.permutation(lean)                 # same law, no signal
    weights = np.abs(rng.normal(1.0, 0.3, n))
    weights = weights / weights.mean()
    got = walkeval.paired_verdict(lean, rich, weights=weights)
    assert abs(got["mean_difference"]) < (cal.SELECT_SE_MULTIPLE
                                          * got["standard_error"])
    assert got["adopted"] is False
    def evaluate(axes):
        return rich if tuple(axes["channels"]) == (0, 1, 2) else lean
    axes, _losses, _detail = autoknobs.choose(
        {"channels": (0,)}, {"channels": autoknobs.CHANNEL_CANDIDATES},
        evaluate, order=("channels",), weights=weights)
    assert axes["channels"] == (0,)


@pytest.mark.parametrize("direction", ["adopt-if-better", "nested-richer"])
def test_a_permuted_halo_does_not_move_the_walk_on_the_real_page(
        world: World, direction: str):
    """The same control end to end: shuffle the FIT-fold target bits.

    A filter fitted on shuffled labels reads at CHANCE, and so does the
    walk's own objective: every population's baseline log loss sits at
    log 2.  The walk still moves an axis here and there — a finite fold
    has noise, and the bar is 2 SE and not a proof — but nothing it
    reads carries signal, which is what a permutation control is for.
    What survives the noise is the ADMISSION: no tier is fitted, every
    cell falls to the box mean, and the filter takes nothing.

    BOTH DIRECTIONS, and the channel assertion only under the retired
    one (2026-09-07 review).  This test ran `adopt-if-better` while
    asserting a property of the shipped path; under `nested-richer` the
    channel axis IS carried to `rgb` by noise, because a tie goes to the
    richer model — the ruling's own rule (§3(b) W3), not an artefact,
    and harmless precisely because the admission still refuses
    everything.
    """
    rng = np.random.default_rng(23)
    frame = world.frame
    bits = np.array(frame.bits, np.uint8, copy=True)
    rows = np.flatnonzero(np.asarray(frame.known[:, 0], bool)
                          & np.asarray(world.folds.fit, bool))
    bits[rows, 0] = rng.permutation(bits[rows, 0])
    from dataclasses import replace as dc_replace
    shuffled = dc_replace(frame, bits=bits)
    spec = patch_mod.spec_from_knobs({**AUTO_NAMED_SHRINKAGE,
                                      "walk_franchise": "pooled",
                                      "walk_direction": direction})
    _score, detail = world.score(spec, frame=shuffled)
    #: the walk's own objective reads log 2 on every population
    for tag, entry in detail["auto_detail"].items():
        assert entry["baseline_logloss"] == pytest.approx(
            float(np.log(2.0)), abs=0.02), tag
    #: and the tier admission refuses every one of them, so every cell
    #: falls to the box mean and the filter takes nothing
    assert detail["patch_fitted_states"] == ()
    assert detail["patch_agnostic"]["fitted"] is False
    assert detail["patch_agnostic"]["reason"] == \
        "refused:crossfit_no_better_than_majority"
    assert detail["patch_fallback_cells"] == int(
        np.count_nonzero(world.lfp.observed))
    channels = {tag: choice["channels"]
                for tag, choice in detail["auto_choices"].items()}
    if direction == "adopt-if-better":
        #: the CHANNEL axis is not carried anywhere by noise when the
        #: candidate has to prove a gain
        for tag, got in channels.items():
            assert got == (0,), tag
    else:
        #: under the shipped direction the tie goes richer, and the
        #: control's job is the line below it: nothing is admitted
        assert (0, 1, 2) in set(channels.values()), (
            "the shipped direction carries a tie to the richer model; if "
            "this ever stops being true the tie-break has changed")


# ---------------------------------------------------------- fold discipline

def test_the_walk_counts_search_fold_labels_and_nothing_else(world: World):
    """Nothing the walk reads comes from the select fold (DESIGN §4.8)."""
    spec = patch_mod.spec_from_knobs(AUTO_NAMED_SHRINKAGE)
    _score, detail = world.score(spec)
    frame = world.frame
    known = np.asarray(frame.known[:, 0], bool)
    observed = np.asarray(world.lfp.observed, bool)
    state = (frame.bits[:, 1].astype(int) + 2 * frame.bits[:, 2].astype(int))
    word = np.asarray(frame.furniture_kind, np.int8) == 0
    search = np.asarray(world.folds.search, bool)
    select = np.asarray(world.folds.select, bool)
    for index in (0, 1, 3):
        want = int(np.count_nonzero(known & observed & search & ~word
                                    & (state == index)))
        assert detail["auto_detail"][f"state{index}"]["n_walk_labels"] == want
    pooled = int(np.count_nonzero(known & observed & search))
    assert detail["auto_detail"]["agnostic"]["n_walk_labels"] == pooled
    assert detail["patch_auto_walk_fold"] == "search"
    assert np.count_nonzero(select) > 0, "there IS a select fold to spend"


def test_labels_per_feature_names_its_denominator(world: World):
    """The whole budget argument is read off this number (§4.3)."""
    spec = patch_mod.spec_from_knobs(AUTO_NAMED_SHRINKAGE)
    _score, detail = world.score(spec)
    state3 = detail["patch_states"][3]
    assert state3["n_features"] == 256                # the CHOSEN width
    assert state3["labels_per_feature"] == pytest.approx(
        state3["n_fit_rows"] / 144.0)                 # the INHERITED one
    assert state3["labels_per_feature_chosen"] == pytest.approx(
        state3["n_fit_rows"] / 256.0)


# ------------------------------------------------------------ determinism

def test_two_runs_with_every_mechanism_on_are_bit_identical(world: World):
    knobs = {**AUTO_NAMED_SHRINKAGE, "patch_shrinkage": "auto",
             "walk_weighting": "cargo", "walk_franchise": "pooled",
             "walk_direction": "nested-richer"}
    spec = patch_mod.spec_from_knobs(knobs)
    first_score, first = world.score(spec)
    second_score, second = world.score(spec)
    assert np.array_equal(first_score, second_score, equal_nan=True)
    assert first["auto_verdicts"] == second["auto_verdicts"]
    assert first["auto_choices"] == second["auto_choices"]
    assert first["auto_detail"] == second["auto_detail"]
    #: and every mechanism actually ENGAGED, or this proves nothing
    assert first["patch_walk_cargo_cells"] > 0
    assert first["patch_walk_inner_axis"] == "shrinkage"
    assert all(entry["walk_ess"] is not None
               for entry in first["auto_detail"].values())
    assert any(tuple(choice["channels"]) == (0, 1, 2)
               for choice in first["auto_choices"].values())


# ------------------------------------------------------------------- CLI

def test_the_halo_takes_a_per_plane_spelling_and_says_where_it_came_from():
    from analyzer import cli
    from analyzer import fixedpoint as fp
    from analyzer.types import Exposure
    from types import SimpleNamespace
    parser = cli.build_parser()

    def config(*extra):
        return cli._config(parser.parse_args(
            ["ladder", "--run-dir", "/tmp/x", "--out", "/tmp/o",
             "--profile", "patch", *extra]))

    assert frame_mod.parse_halo_cells(48) == {"C": 48, "M": 48, "Y": 48}
    assert frame_mod.parse_halo_cells("C=48,M=48,Y=32") == {
        "C": 48, "M": 48, "Y": 32}
    for bad in ("C=48", "wide", "C=48,M=48,Y=32,K=1", "C=a,M=1,Y=1"):
        with pytest.raises(frame_mod.HaloError):
            frame_mod.parse_halo_cells(bad)
    plain = config()
    assert plain.halo_cells == {"C": 16, "M": 16, "Y": 32}
    assert plain.halo_from == "profile:patch" and plain.knobs_from == \
        "profile:patch"
    bare = config("--halo-cells", "48")
    assert bare.halo_cells == {"C": 48, "M": 48, "Y": 48}
    named = config("--halo-cells", "C=48,M=48,Y=32")
    assert named.halo_cells == {"C": 48, "M": 48, "Y": 32}
    #: §4.5(ii): the only CLI word was `--halo-cells`, so `knobs_from`
    #: must NOT read `profile:patch+cli` — a reader diffing that one
    #: field would call it a knob-pinned run
    for got in (bare, named):
        assert got.halo_from == "cli"
        assert got.knobs_from == "profile:patch"
    knobbed = config("--knob", "walk_weighting=cargo")
    assert knobbed.knobs_from == "profile:patch+cli"
    assert knobbed.halo_from == "profile:patch"
    inputs = SimpleNamespace(format_ref="L:x@1x1", run_dir="/tmp/x",
                             captures=(), provenance={})
    header = fp._header(inputs, named, Exposure(), 1)
    assert header["halo_cells"] == {"C": 48, "M": 48, "Y": 32}
    assert header["halo_from"] == "cli"
    assert header["knobs_from"] == "profile:patch"


def test_two_of_the_three_walk_knobs_ship_on_and_a_typo_is_refused():
    """§5's isolation flipped the two that passed, and only those.

    The FRANCHISE (+4) and the DIRECTION (+6) cleared the pre-registered
    gate on 153 open C tile-streams at one code state; the WEIGHTING did
    not (−3, a strict subset of the same run without it) and stays off,
    recorded as a measured negative.  One sheet: regression evidence,
    nothing promoted.
    """
    spec = patch_mod.spec_from_knobs({})
    assert spec.walk_weighting == "none"
    assert spec.walk_franchise == "pooled"
    assert spec.walk_direction == "nested-richer"
    off = patch_mod.spec_from_knobs(WALK_OFF)
    assert (off.walk_weighting, off.walk_franchise, off.walk_direction) == \
        ("none", "inherit", "adopt-if-better")
    assert patch_mod.WALK_KNOBS == ("walk_weighting", "walk_franchise",
                                    "walk_direction")
    #: none of the three is `"auto"`-able: they name HOW a run decides
    for knob in patch_mod.WALK_KNOBS:
        assert knob.removeprefix("walk_") not in patch_mod.AUTO_AXES
        with pytest.raises(patch_mod.PatchError):
            patch_mod.spec_from_knobs({knob: "auto"})
    with pytest.raises(patch_mod.PatchError):
        patch_mod.spec_from_knobs({"walk_franchise": "poooled"})


def test_pava_floors_are_the_ones_the_verdict_still_refuses_below():
    #: `pava.CAL_MIN_HELDOUT == 10` itself is pinned in
    #: `test_analyzer_autoknobs.py`; what is under test here is what the
    #: verdict DOES below it.
    short = walkeval.paired_verdict(np.zeros(9), np.ones(9),
                                    weights=np.ones(9))
    assert short["adopted"] is False
    assert short["reason"] == "too_few_paired_labels"
    #: a refusal adopts NOTHING in either direction — the population that
    #: cannot vote is W2's business, not the direction rule's
    kept = walkeval.paired_verdict(np.zeros(9), np.ones(9),
                                   direction=walkeval.DIRECTION_KEEP)
    assert kept["adopted"] is False
    with pytest.raises(ValueError):
        walkeval.paired_verdict(np.zeros(20), np.zeros(20),
                                direction="whatever")


@pytest.fixture(scope="module")
def world() -> World:
    return World()

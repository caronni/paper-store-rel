"""W8 B7/B8 — `analyzer.patch`: the walk the run decides, and its caches.

The page and the `World` over it live in `_patch_world.py`; B1's grid,
extraction and discriminant are in `test_analyzer_patch.py`, B3's tiers and
local5 scope in `test_analyzer_patch_tiers.py`.  What is pinned here is
B7's coordinate pass — the window axis the coreless third layer widens, the
tie-break to the inherited value, the blindness of the walk's own fold —
and B8's fast pure pass, which must change no number.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace as dc_replace

import numpy as np
import pytest

from analyzer import arms, calibrate as cal, patch as patch_mod
from analyzer import patchcache, pure as pure_module, unmix
from analyzer.types import Evidence

from ._patch_world import World, _auto_spec, _unknown_y, _walk, d_prime


@pytest.fixture(scope="module")
def world() -> World:
    return World()


# ------------------------------------ W8 B7: the knobs the run decides

def test_auto_knobs_keep_the_inherited_value_and_name_the_axis():
    spec = _auto_spec()
    base = patch_mod.PatchSpec()
    assert spec.auto == patch_mod.AUTO_AXES
    # every field still holds what B1/B3 pinned — the INHERITED fallback
    for name in ("window_cells", "samples_per_cell", "channels", "features",
                 "shrinkage", "min_labels_per_state", "min_labels_agnostic"):
        assert getattr(spec, name) == getattr(base, name), name
    assert spec.bounding_window_cells == 2.0
    assert base.bounding_window_cells == base.window_cells
    # an explicit value still wins, axis by axis
    mixed = _auto_spec(patch_window_cells=2.0, patch_channels="rgb")
    assert "window_cells" not in mixed.auto and mixed.window_cells == 2.0
    assert "channels" not in mixed.auto and mixed.channels == (0, 1, 2)
    assert "shrinkage" in mixed.auto
    assert patch_mod.spec_key(spec) != patch_mod.spec_key(base)
    hash(patch_mod.spec_key(spec))
    with pytest.raises(patch_mod.PatchError):
        dc_replace(base, auto=("nonsense",))


def test_naming_every_knob_is_byte_identical_to_the_wave_as_built(world):
    """Nothing auto = B1/B3's own code path, with an empty auto record."""
    score, detail = world.score()
    assert detail["auto_axes"] == ()
    assert detail["auto_choices"] == {} and detail["auto_losses"] == {}
    assert detail["auto_refused"] == {}
    assert detail["patch_features"] == 144


def test_the_run_chooses_a_wide_window_for_the_coreless_third_layer(world):
    """THE claim of B7, and it is the MEASURED mechanism, discovered blind.

    MEAS §3: the third C layer on an M+Y pile has no dot core — a flat
    deficit spread over the cell and its surround — while every other C
    cell is a dot.  `_state_raster` paints exactly that (a 1.5-cell flat
    kernel for state 3, a half-cell dot otherwise).  Nobody tells the run
    which state is which; it fits both windows on its fit fold, prices
    them on its SEARCH fold (review 2026-09-06: the walk is a within-arm
    search and the select fold is left to the arm choice), and comes back
    with the WIDE window for the coreless state and no wider than the
    inherited one for the dots.
    """
    score, detail = world.score(spec=_auto_spec())
    chosen = detail["auto_choices"]
    print()
    for tag in ("state0", "state1", "state3", "agnostic"):
        print(f"  {tag}: {chosen[tag]}")
    assert chosen["state3"]["window_cells"] == 2.0
    # A DOT STATE NEVER ASKS FOR THE CORELESS WINDOW.  state1 comes back
    # with the narrow one outright; state0's 1.0 candidate does not clear
    # the 2-SE margin against the inherited 1.5 on the search fold (it did
    # on the select fold, which is the fold this walk no longer spends),
    # so the pin here is "never wider than inherited", not an exact width.
    assert chosen["state0"]["window_cells"] <= _auto_spec().window_cells
    assert chosen["state1"]["window_cells"] == 1.0
    assert chosen["state3"]["window_cells"] > chosen["state0"]["window_cells"]
    # the 16-samples candidate collapses onto the lane's own 8 px/cell and
    # therefore never wins; the aperture the page was printed for stays
    assert chosen["state3"]["samples_per_cell"] == 8
    assert chosen["tile"]["aperture_cells"] == world.crops.aperture_cells
    # every candidate's held-out loss is on the record, small numbers
    for tag in ("state0", "state3", "tile"):
        assert 2 <= len(detail["auto_losses"][tag]) <= 9
    assert detail["auto_losses"]["state3"]["window_cells=2"] < detail[
        "auto_losses"]["state3"]["inherited"]
    # ... and the chosen filters read the held-out cells at least as well
    box = world.box_score()
    plain, _plain_detail = world.score()
    target = world.frame.bits[:, 0] == 1
    for state in (0, 1, 3):
        rows = world.heldout(state)
        d_auto = d_prime(score[rows], target[rows])
        d_plain = d_prime(plain[rows], target[rows])
        print(f"  state {state}: held-out d' auto {d_auto:.2f} vs named "
              f"{d_plain:.2f} vs box {d_prime(box[rows], target[rows]):.2f}")
        assert d_auto > d_prime(box[rows], target[rows])
        assert d_auto > 0.95 * d_plain


def test_the_open_y_tile_gets_an_admitted_agnostic_tier_and_a_wide_window(
        world):
    """The live/marginal C row of MEAS §5b, where per-state is unavailable.

    Nothing in the tile proves Y, so the sibling state is unknown on its
    cargo and only the state-agnostic tier can reach those cells.  Under
    `auto` it is admitted on its own cross-fit numbers over the WHOLE fit
    set — not on a label count — and it chooses the wide window the
    coreless third layer needs.
    """
    frame = _unknown_y(world)
    named, named_detail = world.score(frame=frame)
    auto, detail = world.score(spec=_auto_spec(), frame=frame)
    agnostic = detail["patch_agnostic"]
    assert agnostic["fitted"] is True
    assert agnostic["admission"]["reason"] == "admitted"
    assert agnostic["admission"]["n"] == int(agnostic["n_fit_rows"])
    assert detail["patch_agnostic_cells"] == named_detail["patch_agnostic_cells"]
    assert detail["patch_fallback_cells"] == 0
    assert detail["auto_choices"]["agnostic"]["window_cells"] == 2.0
    truth_state = (world.page_bits[world.cells[:, 0], world.cells[:, 1], 1]
                   .astype(int)
                   + 2 * world.page_bits[world.cells[:, 0],
                                         world.cells[:, 1], 2].astype(int))
    proven = (np.asarray(frame.known[:, 1], bool)
              & np.asarray(frame.known[:, 2], bool))
    rows = np.flatnonzero(~proven & (truth_state == 3))
    assert rows.size > 100
    target = world.frame.bits[:, 0] == 1
    d_auto = d_prime(auto[rows], target[rows])
    d_named = d_prime(named[rows], target[rows])
    d_box = d_prime(world.box_score()[rows], target[rows])
    print(f"\nopen-Y three-ink cells: d' auto {d_auto:.2f} vs named "
          f"{d_named:.2f} vs box {d_box:.2f} over {rows.size} cells")
    assert d_auto > d_named > d_box


def test_a_decoder_pseudo_bit_is_not_reproduced_at_its_own_cell(world):
    """RULING 7 reaches the decoder's rows (review 2026-09-06).

    P3's pseudo rows used to be `always` — in both cross-fit halves, in
    the full fit, and SCORED BY THE FULL FIT at their own cells.  A
    random bit therefore came back as its own sign, and `calibrate` then
    took that in-sample score as a PAVA training pair while BP took it as
    channel evidence at the map's ceiling.  Cross-fitted, a random bit is
    reproduced at chance and a TRUE one is reproduced because the cell is
    really inked, not because it was labelled.  MEASURED on this world:
    0.505 cross-fitted against 0.613 with the rows left `always`.
    """
    rows = np.flatnonzero(world.fp.in_tile & world.fp.cargo
                          & ~world.frame.known[:, 0]
                          & np.asarray(world.lfp.observed, bool))[:600]
    assert rows.size == 600
    truth = world.page_bits[world.cells[rows, 0], world.cells[rows, 1], 0]
    rng = np.random.default_rng(20260906)
    random_bits = rng.integers(0, 2, rows.size).astype(np.uint8)
    weights = np.full(rows.size, 3.0)
    spec = patch_mod.spec_from_knobs({})
    fed, detail = world.score(spec=spec,
                              extra_labels=(rows, random_bits, weights))
    agreement = float(np.mean((fed[rows] > 0.0) == (random_bits == 1)))
    with_truth = float(np.mean((fed[rows] > 0.0) == (truth == 1)))
    print(f"\n  random pseudo bit reproduced at {agreement:.3f}, "
          f"the true bit at {with_truth:.3f}")
    assert agreement < 0.56, "an in-sample score reproduces its own label"
    assert with_truth > 0.85, "the cell is still read"
    # every pseudo row of every fitted population took an out-of-fold score
    scored = sum(int(entry.get("n_extra_out_of_fold", 0))
                 for entry in detail["patch_states"].values())
    scored += int(detail["patch_agnostic"].get("n_extra_out_of_fold", 0))
    assert scored == rows.size
    assert detail["patch_n_extra_labels"] == rows.size


def test_a_decoder_row_is_never_also_a_self_training_label(world):
    """P2's pool excludes the decoder's cells (review 2026-09-06).

    A pseudo cell whose own sign came back as a self label would be the
    decoder's belief counted a second time, at a second weight.
    """
    rows = np.flatnonzero(world.fp.in_tile & world.fp.cargo
                          & ~world.frame.known[:, 0]
                          & np.asarray(world.lfp.observed, bool))
    bits = world.page_bits[world.cells[rows, 0], world.cells[rows, 1], 0]
    spec = patch_mod.spec_from_knobs({"patch_selftrain_rounds": 2})
    _plain, plain = world.score(spec=spec)
    _fed, fed = world.score(spec=spec,
                            extra_labels=(rows, np.asarray(bits, np.uint8),
                                          np.full(rows.size, 3.0)))
    # every in-tile cargo cell of a state is now a decoder row, so that
    # state's self-training pool is empty and P2 contributes nothing
    assert plain["patch_self_cells"] > 0
    assert fed["patch_self_cells"] == 0


def test_the_walk_never_reads_a_select_fold_label(world):
    """DESIGN §4.8's fold contract, one level down (review 2026-09-06).

    A knob walk MINIMISES, so it is given the SEARCH fold and the select
    fold is left to `select_arm`, `platt` and `best`.  Permute the target
    plane's bits at every select-fold labelled cell: if a single one of
    them reached the walk, some candidate's loss would move and the
    choice could move with it.  Nothing moves.
    """
    bits = np.asarray(world.frame.bits, np.uint8).copy()
    select_rows = np.flatnonzero(world.frame.known[:, 0] & world.folds.select)
    assert select_rows.size > 200
    bits[select_rows, 0] ^= 1
    permuted = dc_replace(world.frame, bits=bits)
    _base, honest = world.score(spec=_auto_spec())
    _other, moved = world.score(spec=_auto_spec(), frame=permuted)
    assert honest["auto_choices"] == moved["auto_choices"]
    assert honest["auto_losses"] == moved["auto_losses"]
    assert honest["auto_axes"] == moved["auto_axes"]
    assert honest["patch_auto_walk_fold"] == "search"


def test_an_auto_arm_forfeits_its_nested_cv_number(world):
    """`select_arm` refuses `heldout_logloss_search` for a knob-walker.

    The walk minimises the search fold exactly as an offset grid does, so
    the winner's search loss is a minimum and may not be reported as
    nested CV (review 2026-09-06; `SEARCHED_REGISTER_ARMS` is the same
    rule for the registration searches).
    """
    default = _evidence_stub("subtract+offset", {})
    walker = _evidence_stub("patch+committed",
                            {"auto_choices": {"state3": {"window_cells": 2.0}},
                             "heldout_logloss_search": 0.11})
    plain = _evidence_stub("patch+committed",
                           {"auto_choices": {},
                            "heldout_logloss_search": 0.11})
    _winner, detail = cal.select_arm([walker, default], world.folds)
    assert detail["winner"] == "patch+committed"
    assert detail["nested_cv_logloss"] is None
    assert detail["nested_cv_refused"] == \
        "winner_chose_its_own_knobs_on_the_search_fold"
    _winner, detail = cal.select_arm([plain, default], world.folds)
    assert detail["winner"] == "patch+committed"
    assert detail["nested_cv_logloss"] == 0.11
    assert detail["nested_cv_refused"] is None


def _evidence_stub(arm: str, blind: dict) -> Evidence:
    """One `select_arm` candidate: paired labels, the loser deliberately
    worse so the non-default arm wins and its nested-CV line is reached."""
    rows = np.arange(400, dtype=np.int64)
    values = (rows % 2).astype(np.uint8)
    good = np.where(values == 1, 6.0, -6.0)
    poor = np.where(values == 1, 0.4, -0.4)
    llr = poor if arm == cal.DEFAULT_ARM else good
    return Evidence(
        key=(0, 0, 0, "C"), lane=("cap", 0), arm=arm,
        llr_sequential=np.zeros(4096), observed=np.zeros(4096, bool),
        blind={"register_arm": arm.partition("+")[2], "label_rows": rows,
               "label_values": values, "label_llr": llr,
               "label_discriminating": np.ones(rows.size, bool), **blind})


def test_the_admission_rule_refuses_every_tier_under_shuffled_labels(world):
    """The permutation control, one level stronger than B1's.

    With the label COUNT pin replaced by `autoknobs.admit`, a filter
    fitted on shuffled labels is not merely collapsed to chance — it is
    REFUSED, tier by tier, on its own cross-fit numbers, and the tile
    falls back to `subtract` everywhere.
    """
    bits = np.asarray(world.frame.bits, np.uint8).copy()
    fit_rows = np.flatnonzero(world.frame.known[:, 0] & world.folds.fit)
    rng = np.random.default_rng(1)
    bits[fit_rows, 0] = bits[rng.permutation(fit_rows), 0]
    shuffled = dc_replace(world.frame, bits=bits)
    _score, detail = world.score(spec=_auto_spec(), frame=shuffled)
    assert detail["patch_fitted_states"] == ()
    assert detail["patch_agnostic"]["fitted"] is False
    assert detail["patch_fallback_cells"] == int(
        np.count_nonzero(world.lfp.observed))
    print()
    for state in (0, 1, 3):
        entry = detail["patch_states"][state]
        admission = entry["admission"]
        print(f"  state {state}: e_in {admission['error_insample']:.3f} "
              f"e_oof {admission['error_crossfit']:.3f} "
              f"majority {admission['majority_rate']:.3f} "
              f"-> {admission['reason']}")
        assert entry["reason"].startswith("refused:")
        assert admission["reason"] in ("crossfit_no_better_than_majority",
                                       "optimism_exceeds_the_gain")
        assert admission["error_crossfit"] > admission["error_insample"]
    # ... and the HONEST labels are admitted on the same page
    _s, honest = world.score(spec=_auto_spec())
    for state in (0, 1, 3):
        assert honest["patch_states"][state]["admission"]["reason"] == \
            "admitted"


def test_the_auto_spec_travels_through_the_unmix_dispatch_arms_uses(world):
    """`arms.evidence_for` reaches the filter through `unmix_score` with a
    (crops, read, lfp, folds, spec) context; an auto spec must arrive
    there whole — that is the only door a real pass uses."""
    spec = _auto_spec()
    context = (world.crops, world.read, world.lfp, world.folds, spec)
    got = unmix.unmix_score("patch", 0, world.mix, world.read.values_rgb,
                            world.frame, context=context)
    direct, _detail = world.score(spec=spec)
    assert np.array_equal(got, direct, equal_nan=True)
    assert patch_mod.objective_mode("patch", spec, grid=True) == "subtract"


def test_the_auto_score_is_deterministic_in_process_and_across_threads(world):
    spec = _auto_spec()
    first, first_detail = world.score(spec=spec)
    second, second_detail = world.score(spec=spec)
    assert np.array_equal(first, second, equal_nan=True)
    assert first_detail["auto_choices"] == second_detail["auto_choices"]
    assert first_detail["auto_losses"] == second_detail["auto_losses"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _i: world.score(spec=spec)[0],
                                range(2)))
    for result in results:
        assert np.array_equal(first, result, equal_nan=True)


def test_the_auto_record_is_small_and_carries_no_arrays(world):
    _score, detail = world.score(spec=_auto_spec())
    _walk(detail["auto_choices"], "auto_choices")
    _walk(detail["auto_losses"], "auto_losses")
    _walk(detail["auto_refused"], "auto_refused")
    _walk(detail["auto_axes"], "auto_axes")
    assert len(json.dumps(
        {key: detail[key] for key in ("auto_axes", "auto_choices",
                                      "auto_losses", "auto_refused")},
        default=str)) < 4096


def test_a_named_axis_is_not_re_chosen_and_the_rings_arm_keeps_its_name(
        world):
    named = _auto_spec(patch_window_cells=2.0)
    _score, detail = world.score(spec=named)
    for tag, chosen in detail["auto_choices"].items():
        assert "window_cells" not in chosen, tag
        assert "shrinkage" in chosen or tag == "tile"
    # the ARM decides the feature kind for `rings+offset`; a select-fold
    # vote there would make it a different arm from the one recorded
    _score, rings = world.score(spec=_auto_spec(), mode="rings")
    assert rings["patch_feature_kind"] == "rings"
    assert rings["auto_refused"]["features"].startswith("the arm names")
    for chosen in rings["auto_choices"].values():
        assert "features" not in chosen


def test_the_patch_and_pure_profiles_ask_the_run_to_decide():
    from analyzer.types import PROFILES
    for name in ("patch", "patch-self", "patch-refit", "patch-affine",
                 "everything+patch"):
        spec = patch_mod.spec_from_knobs(PROFILES[name]["knobs"])
        assert spec.auto == patch_mod.AUTO_AXES, name
    for name in ("pure", "pure-self", "pure-refit"):
        knobs = PROFILES[name]["knobs"]
        spec = patch_mod.spec_from_knobs(knobs)
        # the 5x5 loader extracted its rows through ONE grid, so the
        # samples axis stays NAMED in this family (types.py says why)
        assert "samples_per_cell" not in spec.auto, name
        assert spec.samples_per_cell == 16
        assert set(spec.auto) == set(patch_mod.AUTO_AXES) - {
            "samples_per_cell"}


# ------------------------------------------------ W8 B8: the fast pure pass

AUTO_SPEC = patch_mod.PatchSpec(
    auto=("samples_per_cell", "window_cells", "channels", "features",
          "shrinkage", "min_labels_per_state", "min_labels_agnostic"))


@pytest.fixture(scope="module")
def auto_baseline(world):
    """ONE full-auto pass, shared by the legs that compare against it."""
    return world.score(spec=AUTO_SPEC)


def _raw_row_crossfit(bank, axes, token, positions, labels, half, *,
                      shrinkage):
    """W8 B1/B3's arithmetic: three fits per candidate, from raw rows."""
    block, _inside = bank.selection(axes)
    return patch_mod.crossfit_scores(
        np.asarray(block[positions], np.float64), labels, None, half,
        shrinkage=float(shrinkage))


def test_the_walk_resamples_once_however_many_candidates_it_visits(world,
                                                                  monkeypatch):
    """W8 B8's headline: the coordinate pass is no longer a resampler.

    `map_coordinates` reads about 5.6 M points a second on this machine
    while a 4096x576 normal-equation build takes 25 ms, so the patch
    family was bound by the RESAMPLER.  Under `"auto"` the pass used to
    cut the bounding geometry over every observed cell (only to learn
    which rows fit the crop), the inherited geometry over them again, and
    the selection rows once per candidate per population.  It now cuts
    the selection rows ONCE and the scored rows once.
    """
    calls: list[int] = []
    real = patchcache.extract

    def counted(*args, **kwargs):
        calls.append(int(np.asarray(args[4]).size))
        return real(*args, **kwargs)

    monkeypatch.setattr(patchcache, "extract", counted)
    score, detail = world.score(spec=AUTO_SPEC)
    assert detail["auto_axes"]
    assert detail["auto_choices"], "the walk must have run"
    observed = int(np.count_nonzero(world.lfp.observed))
    # one cut of the scored rows, one of the selection rows, and at most
    # one more for a population that CHOSE a geometry wider than the
    # inherited one (its scored rows have to be resampled there)
    assert len(calls) <= 2 + patch_mod.statecal.N_STATES
    assert sum(calls) < 4 * observed
    assert np.isfinite(score[world.lfp.observed]).all()


def test_the_memoised_and_direct_paths_agree_byte_for_byte(world, monkeypatch,
                                                           auto_baseline):
    """The caches are an economy, not a decision.

    Two dials are turned off together — the walk's single bounding
    extraction (so every candidate is resampled for itself) and the
    full-footprint block memo — and the tile comes back with the same
    scores to the last bit and the same choices.
    """
    base_score, base_detail = auto_baseline
    real = patchcache.FeatureBank.use_selection

    def unbounded(self, rows, bounding=None):
        return real(self, rows, None)

    monkeypatch.setattr(patchcache.FeatureBank, "use_selection", unbounded)
    monkeypatch.setattr(patchcache.FeatureBank, "CACHE_ENTRIES", 0)
    slow_score, slow_detail = world.score(spec=AUTO_SPEC)
    assert np.array_equal(base_score, slow_score, equal_nan=True)
    assert base_detail["auto_choices"] == slow_detail["auto_choices"]
    assert base_detail["patch_fitted_states"] == \
        slow_detail["patch_fitted_states"]


def test_the_moment_path_reaches_the_same_verdicts_as_the_raw_row_fits(
        world, monkeypatch, auto_baseline):
    """`crossfit_selection` against `crossfit_scores`, candidate by candidate.

    The normal-equation form loses the usual digit of a moment-form
    variance (the features are pixel values in [0, 1]), so the two paths
    are compared as numbers, not as bytes — and what must match exactly
    is the DECISION: the same axes chosen for every population, the same
    tiers admitted.
    """
    fast_score, fast_detail = auto_baseline
    monkeypatch.setattr(patch_mod.autoknobs, "crossfit_selection",
                        _raw_row_crossfit)
    slow_score, slow_detail = world.score(spec=AUTO_SPEC)
    assert fast_detail["auto_choices"] == slow_detail["auto_choices"]
    assert fast_detail["patch_fitted_states"] == \
        slow_detail["patch_fitted_states"]
    observed = np.asarray(world.lfp.observed, bool)
    assert np.allclose(fast_score[observed], slow_score[observed],
                       atol=1e-7, rtol=1e-5)


def test_the_pure_mode_is_the_patch_score_under_another_name(world):
    """`pure+…` differs from `patch+…` in the CALIBRATION, nowhere else."""
    assert patch_mod.UNMIX_PURE == "pure"
    assert patch_mod.UNMIX_PURE in patch_mod.PATCH_MODES
    assert "pure" in unmix.UNMIX_MODES
    assert arms.parse_arm("pure+committed") == ("pure", "committed")
    patched, patch_detail = world.score(mode="patch")
    pure, pure_detail = world.score(mode="pure")
    assert np.array_equal(patched, pure, equal_nan=True)
    assert patch_detail["patch_fitted_states"] == \
        pure_detail["patch_fitted_states"]
    # the arm names the calibration; the knob bag names it for everyone
    assert pure_module.is_pure({}, "pure")
    assert not pure_module.is_pure({}, "patch")
    assert pure_module.is_pure({"calibration": "pure"}, "patch")
    assert not pure_module.is_pure({})
    # ... and the objective a search evaluates is unchanged
    assert patch_mod.objective_mode("pure", world.spec, grid=True) == \
        "subtract"

"""W8 B1 — `analyzer.patch`: the grid, the extraction, the discriminant.

The page, the `World` that assembles it and the helpers over it live in
`_patch_world.py`; B3's tiers and local5 scope are in
`test_analyzer_patch_tiers.py`, B7's walk and B8's caches in
`test_analyzer_patch_walk.py`.  The pins that matter here are the blind
ones: the fit sees fit-fold labels and nothing else, the halves are out of
fold, shuffled labels collapse the filter, word sites leave the per-state
fits, and every population leaves the module on one scale.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace as dc_replace

import numpy as np
import pytest

from holo.receiver.lib import spectral

from analyzer import arms, calibrate as cal, ledger, patch as patch_mod
from analyzer import patchgrid as patchgrid_mod, sample, unmix
from analyzer.types import Evidence

from ._patch_world import (CELL_DOTS, ORIGIN_X, ORIGIN_Y, PITCH_PX, World,
                           _footprint, _lane, _placement, _walk, d_prime)


@pytest.fixture(scope="module")
def world() -> World:
    return World()


# ------------------------------------------------------------- the grid

def test_grid_is_window_times_samples_per_cell_capped_at_native_pitch():
    spec = patch_mod.PatchSpec(window_cells=1.5, samples_per_cell=8)
    assert patch_mod.grid_shape(spec, 8.0) == (8, 12)
    grid = patch_mod.grid_cells(spec, 8.0)
    assert grid.shape == (144, 2)
    assert np.isclose(grid[:, 0].min(), 0.5 / 8 - 0.75)
    assert np.isclose(grid[:, 0].max(), 11.5 / 8 - 0.75)
    assert np.isclose(grid[:, 0].mean(), 0.0) and np.isclose(
        grid[:, 1].mean(), 0.0)
    # capped at the lane's native pitch (ruling 4): 36 features at 1200
    assert patch_mod.grid_shape(spec, 4.0) == (4, 6)
    assert patch_mod.grid_cells(spec, 4.0).shape == (36, 2)
    sixteen = patch_mod.PatchSpec(samples_per_cell=16)
    assert patch_mod.grid_shape(sixteen, 16.0) == (16, 24)       # 576
    assert patch_mod.grid_shape(sixteen, 8.0) == (8, 12)         # capped
    assert patch_mod.grid_shape(patch_mod.PatchSpec(window_cells=2.0),
                                16.0) == (8, 16)


# ------------------------------------------------------- the extraction

def test_extract_recovers_the_checkerboard_under_an_off_diagonal_pose():
    """(a, b, c, d, e, f) = (0, P, oy, P, 0, ox) TRANSPOSES the page: the
    sample at grid offset (+1 cell, 0) must read the cell BELOW and
    (0, +1 cell) the cell to the RIGHT.  A transposed grid reads them
    the other way round and must not pass."""
    shape = (24, 24)
    affine = (0.0, PITCH_PX, ORIGIN_Y, PITCH_PX, 0.0, ORIGIN_X)
    gy, gx = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                         indexing="ij")
    value = ((gy * 7 + gx * 13) % 17) / 17.0
    matrix = np.asarray(affine).reshape(2, 3)
    pitch = int(PITCH_PX)
    extent = int(np.ceil((np.array(shape) + 1.5) @ np.abs(matrix[:, :2]).T
                         + np.abs(matrix[:, 2])).max()) + 4 * pitch
    plane = np.zeros((extent, extent), np.float64)
    for cy in range(shape[0]):
        for cx in range(shape[1]):
            centre = np.array((cy + 0.5, cx + 0.5)) @ matrix[:, :2].T \
                + matrix[:, 2]
            y0, x0 = int(round(centre[0])) - pitch // 2, \
                int(round(centre[1])) - pitch // 2
            plane[y0:y0 + pitch, x0:x0 + pitch] = value[cy, cx]
    raster = np.clip(np.round(plane * 255.0), 0, 255).astype(np.uint8)
    lane = _lane((raster, raster, raster), _placement(shape, affine))
    fp = _footprint((0, shape[0]), (0, shape[1]), shape)
    lfp = sample.lane_footprint(lane, fp)
    crops = sample.open_crops(lane, lfp, bound_dots=2 * CELL_DOTS,
                              cell_dots=CELL_DOTS, keep_raw=True)
    read = sample.read_rgb(crops, lfp)
    assert read.refusal is None
    quantised = np.round(value * 255.0) / 255.0
    cells = fp.page_cells_yx
    assert np.allclose(read.values_rgb[:, 0],
                       quantised[cells[:, 0], cells[:, 1]], atol=1e-6)
    interior = np.flatnonzero((cells[:, 0] < shape[0] - 1)
                              & (cells[:, 1] < shape[1] - 1))
    grid = np.array([[1.0, 0.0], [0.0, 1.0]])          # (y, x) cells
    features, inside = patch_mod.extract(
        crops, read.points_yx, read.linear_by_owner, lfp.owner_index,
        interior, grid, (0,))
    assert inside.all()
    below = quantised[cells[interior, 0] + 1, cells[interior, 1]]
    right = quantised[cells[interior, 0], cells[interior, 1] + 1]
    assert np.allclose(features[:, 0], below, atol=1e-6)
    assert np.allclose(features[:, 1], right, atol=1e-6)
    swapped, _inside = patch_mod.extract(
        crops, read.points_yx, read.linear_by_owner, lfp.owner_index,
        interior, grid[:, ::-1], (0,))
    assert not np.allclose(swapped[:, 0], below, atol=1e-3)
    assert np.allclose(swapped[:, 0], right, atol=1e-6)


def test_extract_refuses_outside_the_crop_and_never_clamps():
    tight = World(bound_dots=0.0)                # halo_px = points_halo = 8
    assert tight.crops.halo_px == 8
    wide = patch_mod.PatchSpec(window_cells=3.0)     # ±11.5 px > 8
    grid = patch_mod.grid_cells(wide, PITCH_PX)
    rows = np.arange(tight.cells.shape[0])
    features, inside = patch_mod.extract(
        tight.crops, tight.read.points_yx, tight.read.linear_by_owner,
        tight.lfp.owner_index, rows, grid, (0,))
    cells = tight.cells
    edge = ((cells[:, 0] == 0) | (cells[:, 1] == 0)
            | (cells[:, 0] == cells[:, 0].max())
            | (cells[:, 1] == cells[:, 1].max()))
    assert not inside[edge].any()
    assert np.isnan(features[edge]).all()
    assert inside[~edge].all()
    assert np.isfinite(features[~edge]).all()
    # a row one cell in from the edge is INSIDE and is the honest bilinear
    # read of the raw crop, not a clamped one
    row = int(np.flatnonzero((cells[:, 0] == 1) & (cells[:, 1] == 1))[0])
    centre = tight.read.points_yx[row] - (tight.crops.y0, tight.crops.x0)
    corner = centre + grid[0] @ tight.read.linear_by_owner[0].T
    assert corner.min() >= 0.0
    raw = tight.crops.raw_rgb[..., 0].astype(np.float64) / tight.crops.divisor
    y, x = corner
    iy, ix = int(np.floor(y)), int(np.floor(x))
    fy, fx = y - iy, x - ix
    manual = ((1 - fy) * (1 - fx) * raw[iy, ix] + (1 - fy) * fx * raw[iy, ix + 1]
              + fy * (1 - fx) * raw[iy + 1, ix] + fy * fx * raw[iy + 1, ix + 1])
    assert np.isclose(features[row, 0], manual, atol=1e-5)
    # the default 1.5-cell window (±5.5 px) fits the 8-px halo everywhere
    narrow = patch_mod.grid_cells(patch_mod.PatchSpec(), PITCH_PX)
    _features, inside_all = patch_mod.extract(
        tight.crops, tight.read.points_yx, tight.read.linear_by_owner,
        tight.lfp.owner_index, rows, narrow, (0,))
    assert inside_all.all()


def test_extract_is_chunked_and_identical_to_one_shot(world, monkeypatch):
    grid = patch_mod.grid_cells(world.spec, PITCH_PX)
    rows = np.arange(world.cells.shape[0])
    one_shot, inside_one = patch_mod.extract(
        world.crops, world.read.points_yx, world.read.linear_by_owner,
        world.lfp.owner_index, rows, grid, (0, 1, 2))
    # W8 B3 moved the extraction to `patchgrid` (DESIGN §0.4's cap);
    # `extract` reads the chunk size from ITS module's globals.
    monkeypatch.setattr(patchgrid_mod, "EXTRACT_CHUNK_ROWS", 97)
    chunked, inside_chunked = patch_mod.extract(
        world.crops, world.read.points_yx, world.read.linear_by_owner,
        world.lfp.owner_index, rows, grid, (0, 1, 2))
    assert np.array_equal(one_shot, chunked, equal_nan=True)
    assert np.array_equal(inside_one, inside_chunked)
    assert one_shot.shape == (rows.size, 3 * 144)
    assert one_shot.dtype == np.float32


def test_extract_needs_the_raw_crop():
    plain = World(keep_raw=False)
    assert plain.crops.raw_rgb is None
    with pytest.raises(patch_mod.PatchError):
        patch_mod.extract(plain.crops, plain.read.points_yx,
                          plain.read.linear_by_owner, plain.lfp.owner_index,
                          np.arange(4), patch_mod.grid_cells(plain.spec, 8.0),
                          (0,))
    with pytest.raises(patch_mod.PatchError):
        plain.score()


# ---------------------------------------------------- the discriminant

def _fit_lda_reference(X, yv, wt=None, lam=1e-2):
    """`measure/c-third-layer-20260906/analyze_selftrain.py:fit_lda`."""
    wt = np.ones(len(yv)) if wt is None else wt
    wt = wt / wt.sum()
    mu = (wt[:, None] * X).sum(0)
    Xs = X - mu
    sd = np.sqrt((wt[:, None] * Xs ** 2).sum(0)) + 1e-6
    Xs = Xs / sd
    t = np.where(yv == 1, 1.0, -1.0)
    A = (Xs * wt[:, None]).T @ Xs + lam * np.eye(X.shape[1])
    wv = np.linalg.solve(A, (Xs * wt[:, None]).T @ t)
    s = Xs @ wv
    thr = 0.5 * ((wt * (yv == 1) * s).sum() / (wt * (yv == 1)).sum()
                 + (wt * (yv == 0) * s).sum() / (wt * (yv == 0)).sum())
    return mu, sd, wv, thr


def test_discriminant_matches_the_measurement_recipe():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(300, 20))
    y = (rng.random(300) < 0.4).astype(np.uint8)
    X[y == 1, :5] += 0.8
    w = rng.uniform(0.5, 3.0, 300)
    mu, sd, wv, thr = _fit_lda_reference(X, y, w)
    fitted = patch_mod.fit_discriminant(X, y, w, shrinkage=1e-2)
    assert np.allclose(fitted.mu, mu, atol=1e-9)
    assert np.allclose(fitted.sd, sd, atol=1e-9)
    assert np.allclose(fitted.w, wv, atol=1e-9)
    assert np.isclose(fitted.threshold, thr, atol=1e-9)
    assert (fitted.n_0, fitted.n_1) == (int((y == 0).sum()),
                                        int((y == 1).sum()))
    expect = ((X - mu) / sd) @ wv - thr
    assert np.allclose(patch_mod.apply_discriminant(X, fitted), expect,
                       atol=1e-9)
    with pytest.raises(patch_mod.PatchError):
        patch_mod.fit_discriminant(X, np.zeros(300, np.uint8))


def test_crossfit_scores_are_out_of_fold_on_every_training_row():
    rng = np.random.default_rng(5)
    X = rng.normal(size=(400, 12))
    y = (rng.random(400) < 0.5).astype(np.uint8)
    X[y == 1, :3] += 1.0
    half = rng.random(400) < 0.5
    oof, full = patch_mod.crossfit_scores(X, y, None, half, shrinkage=1e-2)
    fit_a = patch_mod.fit_discriminant(X[half], y[half])
    fit_b = patch_mod.fit_discriminant(X[~half], y[~half])
    raw = np.empty(400)
    raw[~half] = patch_mod.apply_discriminant(X[~half], fit_a)
    raw[half] = patch_mod.apply_discriminant(X[half], fit_b)
    assert np.isclose(full.scale, np.std(raw))
    assert np.allclose(oof, raw / full.scale)
    # never the full fit's own in-sample score
    insample = patch_mod.apply_discriminant(X, full)
    assert not np.allclose(oof, insample)
    # a row flagged `always` (a pseudo label) is in every fit and takes
    # the full fit's score
    always = np.zeros(400, bool)
    always[:20] = True
    oof2, full2 = patch_mod.crossfit_scores(X, y, None, half, always=always)
    assert np.allclose(oof2[:20], patch_mod.apply_discriminant(X[:20], full2))
    with pytest.raises(patch_mod.PatchError):
        patch_mod.crossfit_scores(X, y, None, np.ones(400, bool))


# ------------------------------------------------------- the score itself

def test_patch_score_fits_per_state_and_falls_back_to_subtract_where_starved(
        world):
    # P1f in isolation: B3's state-agnostic tier (P1d) sits between the
    # per-state filters and `subtract` and would take state 2's cells, so
    # this test — the claim that a STARVED state falls to `subtract` on
    # the shared scale — runs with the agnostic floor out of reach.  The
    # tier itself is
    # `test_the_agnostic_tier_fires_where_siblings_are_unknown_and_has_its_own_floor`.
    no_agnostic = dc_replace(world.spec, min_labels_agnostic=1_000_000)
    score, detail = world.score(spec=no_agnostic)
    states = detail["patch_states"]
    assert [states[s]["fitted"] for s in range(4)] == [True, True, False,
                                                       True]
    assert states[2]["reason"] == "below_min_labels_per_state"
    assert detail["patch_fitted_states"] == (0, 1, 3)
    assert detail["patch_features"] == 144 and detail["patch_px"] == 12
    assert detail["patch_labels_from"] == "halo"
    assert np.isnan(score).sum() == 0            # every cell observed
    box = world.box_score()
    target = world.frame.bits[:, 0] == 1
    print()
    for state in (0, 1, 3):
        rows = world.heldout(state)
        d_patch = d_prime(score[rows], target[rows])
        d_box = d_prime(box[rows], target[rows])
        print(f"state {state}: held-out d' patch {d_patch:.2f} vs box "
              f"{d_box:.2f} over {rows.size} cells "
              f"(fit labels {states[state]['n_fit_0']}/"
              f"{states[state]['n_fit_1']})")
        assert d_patch > d_box
    # the starved state is `subtract`, on the shared scale
    all_states = (world.frame.bits[:, 1].astype(int)
                  + 2 * world.frame.bits[:, 2].astype(int))
    rows2 = np.flatnonzero(all_states == 2)
    assert rows2.size == detail["patch_fallback_cells"] > 0
    expect = ((box[rows2] - detail["patch_fallback_centre_value"])
              / detail["patch_fallback_scale"])
    assert np.allclose(score[rows2], expect)
    assert detail["patch_outside_cells"] == 0
    assert detail["patch_fit_error_crossfit"] >= detail[
        "patch_fit_error_insample"]
    assert detail["patch_fit_error_crossfit"] < 0.15


def test_patch_score_reads_only_fit_fold_labels_and_never_the_targets_own_bit(
        world):
    base, _detail = world.score()
    bits = np.asarray(world.frame.bits, np.uint8).copy()
    # every search- and select-fold bit, and the target's own UNKNOWN
    # cargo (whose bit is never a label): none of it may move the score
    flip = (~np.asarray(world.folds.fit, bool)
            | (np.asarray(world.fp.in_tile, bool)
               & ~np.asarray(world.frame.known[:, 0], bool)))
    assert flip.sum() > world.cells.shape[0] // 2
    bits[flip, 0] ^= 1
    flipped = dc_replace(world.frame, bits=bits)
    moved, _detail = world.score(frame=flipped)
    assert np.array_equal(base, moved, equal_nan=True)
    # ... whereas a FIT-fold label does (the fit is real)
    fit_known = np.flatnonzero(world.frame.known[:, 0] & world.folds.fit
                               & (world.frame.furniture_kind != 0))
    bits = np.asarray(world.frame.bits, np.uint8).copy()
    bits[fit_known[:200], 0] ^= 1
    changed, _detail = world.score(frame=dc_replace(world.frame, bits=bits))
    assert not np.array_equal(base, changed, equal_nan=True)


def test_shuffled_fit_labels_collapse_the_discriminant(world):
    """The blind twin of MEAS §5b's permutation control (0.46)."""
    real, real_detail = world.score()
    bits = np.asarray(world.frame.bits, np.uint8).copy()
    fit_rows = np.flatnonzero(world.frame.known[:, 0] & world.folds.fit)
    rng = np.random.default_rng(1)
    bits[fit_rows, 0] = bits[rng.permutation(fit_rows), 0]
    shuffled_frame = dc_replace(world.frame, bits=bits)
    shuffled, detail = world.score(frame=shuffled_frame)
    target = world.frame.bits[:, 0] == 1           # the TRUE bits
    print()
    for state in (0, 1, 3):
        assert detail["patch_states"][state]["fitted"] is True
        rows = world.heldout(state)
        d_real = d_prime(real[rows], target[rows])
        d_null = d_prime(shuffled[rows], target[rows])
        print(f"state {state}: held-out d' real {d_real:.2f}, shuffled "
              f"labels {d_null:.2f}")
        assert d_real > 2.0
        assert abs(d_null) < 0.35
    assert detail["patch_fit_error_crossfit"] > 0.35
    assert real_detail["patch_fit_error_crossfit"] < 0.15


def test_word_sites_are_excluded_from_per_state_fits_and_counted(world):
    labelled = (world.frame.known[:, 0] & world.folds.fit)
    word = world.frame.furniture_kind == 0
    all_states = (world.frame.bits[:, 1].astype(int)
                  + 2 * world.frame.bits[:, 2].astype(int))
    _score, detail = world.score()
    for state in (0, 3):                 # a word site is state 0 or 3
        entry = detail["patch_states"][state]
        assert entry["n_fit_word"] == int(np.count_nonzero(
            labelled & word & (all_states == state))) > 0
        assert entry["n_fit_0"] + entry["n_fit_1"] == int(np.count_nonzero(
            labelled & ~word & (all_states == state)))
        assert entry["n_fit_dust"] >= 0
    assert detail["patch_exclude_word_sites"] is True
    _score, kept = world.score(
        spec=patch_mod.PatchSpec(exclude_word_sites=False))
    for state in (0, 3):
        entry = kept["patch_states"][state]
        assert entry["n_fit_0"] + entry["n_fit_1"] == int(np.count_nonzero(
            labelled & (all_states == state)))
    assert kept["patch_exclude_word_sites"] is False


def test_populations_share_one_scale(world):
    score, detail = world.score()
    labelled = world.frame.known[:, 0] & world.folds.fit
    all_states = (world.frame.bits[:, 1].astype(int)
                  + 2 * world.frame.bits[:, 2].astype(int))
    for state in range(4):
        rows = np.flatnonzero(labelled & (all_states == state))
        if state in detail["patch_fitted_states"]:
            rows = rows[world.frame.furniture_kind[rows] != 0]
        assert rows.size > 2
        assert np.isclose(np.std(score[rows]), 1.0, atol=1e-6), state


def test_patch_score_is_repeatable_in_process(world):
    first, _d = world.score()
    second, _d = world.score()
    assert np.array_equal(first, second, equal_nan=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _i: world.score()[0], range(4)))
    for result in results:
        assert np.array_equal(first, result, equal_nan=True)


def test_extra_labels_join_the_fit_of_their_state_and_say_so(world):
    """B3/B4's door: pseudo rows are cargo, join the fit set of their
    state with their weight, never the label bookkeeping."""
    all_states = (world.frame.bits[:, 1].astype(int)
                  + 2 * world.frame.bits[:, 2].astype(int))
    cargo3 = np.flatnonzero(world.fp.in_tile & world.fp.cargo
                            & (all_states == 3))[:150]
    base, base_detail = world.score()
    extra = (cargo3, (base[cargo3] > 0).astype(np.uint8),
             np.full(cargo3.size, 2.0))
    moved, detail = world.score(extra_labels=extra)
    assert detail["patch_labels_from"] == "halo+bp"
    assert detail["patch_n_extra_labels"] == cargo3.size
    assert detail["patch_states"][3]["n_extra"] == cargo3.size
    assert detail["patch_states"][3]["n_fit_0"] == base_detail[
        "patch_states"][3]["n_fit_0"]                 # halo counts untouched
    assert not np.array_equal(base, moved)
    # a KNOWN row is never a pseudo row
    known_rows = np.flatnonzero(world.frame.known[:, 0])[:10]
    _s, d2 = world.score(extra_labels=(known_rows, np.zeros(10, np.uint8),
                                       np.ones(10)))
    assert d2["patch_n_extra_labels"] == 0


def test_pseudo_rows_map_page_cells_to_footprint_rows(world):
    class Pseudo:
        cells_yx = np.array([[3, 4], [70, 70], [500, 500], [0, 0]])
        bits = np.array([1, 0, 1, 1], np.uint8)
        weights = np.array([3.0, 3.0, 3.0, 2.0])

    rows, bits, weights = patch_mod.pseudo_rows(world.fp, Pseudo())
    cells = world.cells
    assert rows.tolist() == [int(np.flatnonzero((cells[:, 0] == 3)
                                                & (cells[:, 1] == 4))[0]),
                             int(np.flatnonzero((cells[:, 0] == 70)
                                                & (cells[:, 1] == 70))[0]),
                             0]
    assert bits.tolist() == [1, 0, 1] and weights.tolist() == [3.0, 3.0, 2.0]


# ------------------------------------------------------------ the seams

def test_unmix_score_dispatches_patch_and_refuses_without_context(world):
    assert "patch" in unmix.UNMIX_MODES
    assert patch_mod.PATCH_MODES == ("patch", "rings", "mixture", "pure")
    with pytest.raises(unmix.UnmixError):
        unmix.unmix_score("patch", 0, world.mix, world.read.values_rgb,
                          world.frame)
    context = (world.crops, world.read, world.lfp, world.folds, world.spec)
    got = unmix.unmix_score("patch", 0, world.mix, world.read.values_rgb,
                            world.frame, context=context)
    assert np.array_equal(got, world.score()[0], equal_nan=True)
    # a refused mix is NaN everywhere, before any context is consulted
    refused = spectral.fit_plane_mix(np.zeros((0, 3)),
                                     np.zeros((0, 3), np.uint8),
                                     np.zeros((0, 3), bool))
    assert np.isnan(unmix.unmix_score("patch", 0, refused,
                                      world.read.values_rgb, world.frame)).all()


def test_read_carries_the_pose_and_crops_keep_the_raw_pixels_only_when_asked(
        world):
    plain = sample.open_crops(world.lane, world.lfp, bound_dots=2.5,
                              cell_dots=CELL_DOTS)
    assert plain.raw_rgb is None
    kept = world.crops.raw_rgb
    assert kept is not None and kept.dtype == np.uint8
    assert kept.shape == world.crops.filtered_rgb.shape
    read = world.read
    assert np.allclose(read.points_yx, world.lfp.points_yx)
    assert set(read.linear_by_owner) == {0}
    assert np.array_equal(read.linear_by_owner[0],
                          np.array([[PITCH_PX, 0.0], [0.0, PITCH_PX]]))
    shifted = sample.read_rgb(world.crops, world.lfp,
                              offset_dots_xy=(CELL_DOTS, 0.0))
    assert np.allclose(shifted.points_yx[:, 1],
                       world.lfp.points_yx[:, 1] + PITCH_PX)
    assert np.allclose(shifted.points_yx[:, 0], world.lfp.points_yx[:, 0])
    refused = sample.read_rgb(world.crops, world.lfp,
                              offset_dots_xy=(400.0, 0.0))
    assert refused.refusal is not None
    assert refused.points_yx is None and refused.linear_by_owner is None


def test_every_existing_arm_is_byte_identical_with_raw_crops_off_and_on(
        world):
    off = sample.open_crops(world.lane, world.lfp, bound_dots=2.5,
                            cell_dots=CELL_DOTS, keep_raw=False)
    on = world.crops
    assert np.array_equal(off.filtered_rgb, on.filtered_rgb)
    for offset in ((0.0, 0.0), (CELL_DOTS, 0.0), (0.0, -CELL_DOTS),
                   (0.75, 0.25)):
        a = sample.read_rgb(off, world.lfp, offset_dots_xy=offset)
        b = sample.read_rgb(on, world.lfp, offset_dots_xy=offset)
        assert np.array_equal(a.values_rgb, b.values_rgb, equal_nan=True)
        for mode in ("raw", "project", "subtract", "conditional", "head"):
            assert np.array_equal(
                unmix.unmix_score(mode, 0, world.mix, a.values_rgb,
                                  world.frame, fit_mask=world.folds.fit),
                unmix.unmix_score(mode, 0, world.mix, b.values_rgb,
                                  world.frame, fit_mask=world.folds.fit),
                equal_nan=True)


def test_patch_detail_carries_no_arrays(world):
    _score, detail = world.score()
    _walk(detail)
    json.dumps(ledger.jsonable(detail))
    for name in ("patch_window_cells", "patch_samples_per_cell", "patch_px",
                 "patch_features", "patch_channels", "patch_shrinkage",
                 "patch_fit_fold", "patch_labels_from", "patch_states",
                 "patch_agnostic_cells", "patch_fallback_cells",
                 "patch_outside_cells", "patch_search_mode",
                 "patch_fit_error_insample", "patch_fit_error_crossfit",
                 "patch_crossfit_halves"):
        assert name in detail, name
    for entry in detail["patch_states"].values():
        for name in ("n_fit_0", "n_fit_1", "n_fit_word", "n_fit_dust",
                     "n_fit_cargo", "fitted", "n_scored",
                     "labels_per_feature"):
            assert name in entry, name


def test_patch_arms_parse_and_affine_and_word_search_under_subtract(world):
    for arm in ("patch+offset", "patch+committed", "patch+field2+offset",
                "patch+affine", "patch+word"):
        assert arms.parse_arm(arm)[0] == "patch"
    common = dict(mix=world.mix, cell_dots=CELL_DOTS, spec=world.spec)
    _read, affine = arms.register("affine", world.lane, world.crops,
                                  world.lfp, world.frame, 0, "patch",
                                  world.folds, **common)
    assert affine["register_objective_mode"] == "subtract"
    assert affine.get("refusal") is None
    _read, word = arms.register("word", world.lane, world.crops, world.lfp,
                                world.frame, 0, "patch", world.folds,
                                **common)
    assert word["register_objective_mode"] == "subtract"
    _read, grid = arms.register("committed", world.lane, world.crops,
                                world.lfp, world.frame, 0, "patch",
                                world.folds, **common)
    assert grid["register_objective_mode"] == "subtract"
    # the offset GRID follows the spec (E2 is the grid only)
    assert patch_mod.objective_mode("patch", world.spec, grid=True) == \
        "subtract"
    patchy = patch_mod.PatchSpec(search_mode="patch")
    assert patch_mod.objective_mode("patch", patchy, grid=True) == "patch"
    assert patch_mod.objective_mode("patch", patchy, grid=False) == \
        "subtract"
    assert patch_mod.objective_mode("head", patchy, grid=True) == "head"
    _read, plain = arms.register("affine", world.lane, world.crops,
                                 world.lfp, world.frame, 0, "subtract",
                                 world.folds, **common)
    assert plain["register_objective_mode"] == "subtract"


def test_the_offset_search_under_a_patch_mode_evaluates_subtract(
        world, monkeypatch):
    seen: list[str] = []
    original = arms.unmix_score

    def spy(mode, *args, **kwargs):
        seen.append(mode)
        return original(mode, *args, **kwargs)

    monkeypatch.setattr(arms, "unmix_score", spy)
    arms._search_offset(world.crops, world.lfp, world.frame, world.mix, 0,
                        "patch", world.folds, (0.0, 0.0), None,
                        x_range=(-0.25, 0.25), y_range=(0.0, 0.0),
                        spec=world.spec)
    assert seen and set(seen) == {"subtract"}
    seen.clear()
    arms._search_offset(world.crops, world.lfp, world.frame, world.mix, 0,
                        "patch", world.folds, (0.0, 0.0), None,
                        x_range=(-0.25, 0.25), y_range=(0.0, 0.0),
                        spec=patch_mod.PatchSpec(search_mode="patch"))
    assert seen and set(seen) == {"patch"}


def test_nested_cv_is_refused_for_every_searching_register_arm():
    searching = {arm for arm in arms.REGISTER_ARMS
                 if arm.endswith("offset") or arm in ("affine", "word")}
    assert set(cal.SEARCHED_REGISTER_ARMS) == searching
    assert searching < set(arms.REGISTER_ARMS)
    rows = np.arange(200)
    values = (rows % 2).astype(np.uint8)
    for arm in arms.REGISTER_ARMS:
        evidence = Evidence(
            key=(0, 0, 0, "C"), lane=("cap0", 0), arm=f"subtract+{arm}",
            llr_sequential=np.zeros(8), observed=np.ones(8, bool),
            blind={"register_arm": arm, "label_rows": rows,
                   "label_values": values,
                   "label_llr": np.where(values == 1, 2.0, -2.0),
                   "label_discriminating": np.ones(200, bool),
                   "heldout_logloss_search": 0.31})
        _winner, detail = cal.select_arm([evidence], None)
        if arm in searching:
            assert detail["nested_cv_refused"] == \
                "winner_minimised_the_search_fold", arm
            assert detail["nested_cv_logloss"] is None
        else:
            assert detail["nested_cv_refused"] is None, arm
            assert detail["nested_cv_logloss"] == 0.31


def test_spec_from_knobs_reads_every_patch_knob_and_refuses_nonsense():
    spec = patch_mod.spec_from_knobs({
        "patch_window_cells": 2.0, "patch_samples_per_cell": 16,
        "patch_channels": "rgb", "patch_shrinkage": 0.1,
        "patch_min_labels_per_state": 600, "patch_min_labels_agnostic": 300,
        "patch_search_mode": "patch", "patch_selftrain_rounds": 4,
        "patch_selftrain_keep": 0.5, "patch_selftrain_weight": 3.0,
        "patch_exclude_word_sites": False, "seed": 5})
    assert spec == patch_mod.PatchSpec(
        window_cells=2.0, samples_per_cell=16, channels=(0, 1, 2),
        shrinkage=0.1, min_labels_per_state=600, min_labels_agnostic=300,
        search_mode="patch", selftrain_rounds=4, selftrain_keep=0.5,
        selftrain_weight=3.0, exclude_word_sites=False)
    assert patch_mod.spec_from_knobs(None) == patch_mod.PatchSpec()
    assert patch_mod.spec_from_knobs({"patch_channels": "r"}).channels == (0,)
    assert patch_mod.spec_key(spec) != patch_mod.spec_key(patch_mod.PatchSpec())
    hash(patch_mod.spec_key(spec))
    for bad in ({"patch_channels": "cmyk"}, {"patch_search_mode": "swim"},
                {"patch_window_cells": 0.0}, {"patch_train_scope": "page"}):
        with pytest.raises(patch_mod.PatchError):
            patch_mod.spec_from_knobs(bad)

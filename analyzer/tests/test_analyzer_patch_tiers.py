"""W8 B3 — `analyzer.patch`: the tiers, self-training and the local5 scope.

The page and the `World` over it live in `_patch_world.py`; B1's grid,
extraction and discriminant are in `test_analyzer_patch.py`, B7's walk and
B8's caches in `test_analyzer_patch_walk.py`.  What is pinned here is the
agnostic tier and its own floor, that self-training is deterministic,
bounded and never labels a known row, and that the local5 harvest never
reaches inside the target's own footprint.
"""

from __future__ import annotations

from dataclasses import replace as dc_replace

import numpy as np
import pytest

from analyzer import arms, calibrate as cal, patch as patch_mod
from analyzer import patchgrid as patchgrid_mod, sample

from ._patch_world import (CELL_DOTS, PITCH_PX, World, _auto_spec,
                           _unknown_y, d_prime)


@pytest.fixture(scope="module")
def world() -> World:
    return World()


# ------------------------------------------------ W8 B3: the tiers, P2, M1

def test_the_agnostic_tier_fires_where_siblings_are_unknown_and_has_its_own_floor(
        world):
    frame = _unknown_y(world)
    state = (np.asarray(frame.known[:, 1], bool)
             & np.asarray(frame.known[:, 2], bool))
    orphans = np.flatnonzero(~state)
    assert orphans.size > 500                     # the tile's own cells

    score, detail = world.score(frame=frame)
    assert detail["patch_agnostic"]["fitted"] is True
    assert detail["patch_unknown_state_cells"] == orphans.size
    assert detail["patch_labels_from"] == "halo"
    # it takes the unproven cells AND the cells of a state that refused
    # (state 2 is starved in this page: `_bits` makes Y-alone ~1.5%)
    proven_state = (np.asarray(frame.bits[:, 1], int)
                    + 2 * np.asarray(frame.bits[:, 2], int))
    refused = np.flatnonzero(state & np.isin(
        proven_state, [s for s in range(4)
                       if s not in detail["patch_fitted_states"]]))
    assert detail["patch_states"][2]["reason"] == "below_min_labels_per_state"
    assert detail["patch_agnostic_cells"] == orphans.size + refused.size
    assert detail["patch_fallback_cells"] == 0

    # its OWN floor: out of reach, and those cells are `subtract` again
    starved = dc_replace(world.spec, min_labels_agnostic=1_000_000)
    box_score, box_detail = world.score(spec=starved, frame=frame)
    assert box_detail["patch_agnostic"]["reason"] == "below_min_labels_agnostic"
    assert box_detail["patch_agnostic_cells"] == 0
    assert box_detail["patch_fallback_cells"] == orphans.size + refused.size

    # and it is a real filter: on the tile's own three-ink cells (whose
    # state the frame no longer proves) it beats the box mean it replaced
    truth_state = (world.page_bits[world.cells[:, 0], world.cells[:, 1], 1]
                   .astype(int)
                   + 2 * world.page_bits[world.cells[:, 0],
                                         world.cells[:, 1], 2].astype(int))
    target = world.frame.bits[:, 0] == 1
    rows = np.flatnonzero(~state & (truth_state == 3))
    assert rows.size > 100
    d_agnostic = d_prime(score[rows], target[rows])
    d_box = d_prime(box_score[rows], target[rows])
    print(f"\nagnostic tier on unproven-state three-ink cells: d' "
          f"{d_agnostic:.2f} vs box {d_box:.2f} over {rows.size} cells")
    assert d_agnostic > d_box

    # the permutation control (MEAS §5b read 0.46): shuffle the fit-fold
    # labels the agnostic tier trains on and it must read chance
    bits = np.asarray(frame.bits, np.uint8).copy()
    fit_rows = np.flatnonzero(np.asarray(frame.known[:, 0], bool)
                              & np.asarray(world.folds.fit, bool))
    bits[fit_rows, 0] = bits[fit_rows[::-1], 0]
    shuffled, shuffled_detail = world.score(
        frame=dc_replace(frame, bits=bits))
    assert shuffled_detail["patch_agnostic"]["fitted"] is True
    assert abs(d_prime(shuffled[rows], target[rows])) < 0.5 * d_agnostic


def test_the_per_state_floor_isolates_the_agnostic_tier(world):
    """`patch_min_labels_per_state=1e6` is P1d's isolation (S10), and
    both floors out of reach is P1f's (`subtract` everywhere)."""
    only_agnostic = dc_replace(world.spec, min_labels_per_state=1_000_000)
    score, detail = world.score(spec=only_agnostic)
    assert detail["patch_fitted_states"] == ()
    assert detail["patch_agnostic"]["fitted"] is True
    assert detail["patch_agnostic_cells"] > 0
    assert detail["patch_fallback_cells"] == 0
    nothing = dc_replace(only_agnostic, min_labels_agnostic=1_000_000)
    box, box_detail = world.score(spec=nothing)
    assert box_detail["patch_agnostic_cells"] == 0
    assert box_detail["patch_fallback_cells"] == int(
        np.count_nonzero(world.lfp.observed))
    expect = ((world.box_score() - box_detail["patch_fallback_centre_value"])
              / box_detail["patch_fallback_scale"])
    assert np.allclose(box, expect)
    assert not np.array_equal(score, box, equal_nan=True)


def test_self_training_is_deterministic_bounded_and_never_labels_a_known_row(
        world):
    plain = dc_replace(world.spec, selftrain_rounds=0)
    trained = dc_replace(world.spec, selftrain_rounds=4)
    base, base_detail = world.score(spec=plain)
    selfed, self_detail = world.score(spec=trained)
    assert base_detail["patch_self_cells"] == 0
    assert base_detail["patch_labels_from"] == "halo"
    assert base_detail["pseudo_source"] is None
    assert self_detail["patch_labels_from"] == "halo+self"
    assert self_detail["pseudo_source"] == "self"
    assert self_detail["patch_self_rounds"] == 4
    assert not np.array_equal(base, selfed, equal_nan=True)

    # BOUNDED: the pool is the tile's own cargo the frame does not know,
    # and `keep` of it is labelled per round, per fitted population
    pool = int(np.count_nonzero(np.asarray(world.fp.in_tile, bool)
                                & np.asarray(world.fp.cargo, bool)
                                & ~np.asarray(world.frame.known[:, 0], bool)))
    assert 0 < self_detail["patch_self_cells"] <= pool
    assert self_detail["patch_self_cells"] <= int(
        np.ceil(world.spec.selftrain_keep * pool)) + len(
        self_detail["patch_fitted_states"])

    # DETERMINISTIC: a percentile threshold, never a draw
    again, _detail = world.score(spec=trained)
    assert np.array_equal(selfed, again, equal_nan=True)

    # NEVER A KNOWN ROW.  The metadata cell is the case that matters (it
    # is the one in-tile cargo cell the frame knows); the rule is general,
    # so a frame that knows EVERY in-tile cell has no pseudo row at all.
    known = np.asarray(world.frame.known, bool).copy()
    known[:, 0] = True
    all_known, all_detail = world.score(
        spec=trained, frame=dc_replace(world.frame, known=known,
                                       labels=known[:, 0].copy()))
    assert all_detail["patch_self_cells"] == 0
    assert all_detail["patch_labels_from"] == "halo"
    assert np.isfinite(all_known).all()

    # and the select-fold arrays `calibrate` publishes do not move: a
    # pseudo row is cargo, never a label row (APPROACHES ruling 9)
    def _labels(score_vector):
        _llr, detail = cal.calibrate(score_vector, world.frame, 0, world.lfp,
                                     world.folds)
        return (detail["label_rows"], detail["label_values"],
                detail["label_discriminating"])

    for before, after in zip(_labels(base), _labels(selfed)):
        assert np.array_equal(before, after)


def test_rings_are_more_shift_robust_than_pixels(world):
    """P1c: a radial mean cannot see a rotation and barely sees a shift."""
    rows = np.flatnonzero(np.asarray(world.lfp.observed, bool))
    grid = patch_mod.grid_cells(world.spec, PITCH_PX)
    matrix = patch_mod.ring_matrix(world.spec, PITCH_PX)
    assert matrix.shape == (144, 6)
    assert np.allclose(matrix.sum(axis=0)[matrix.sum(axis=0) > 0], 1.0)

    def _features(read):
        pixels, inside = patch_mod.extract(
            world.crops, read.points_yx, read.linear_by_owner,
            world.lfp.owner_index, rows, grid, (0,))
        return pixels, patch_mod.ring_features(pixels, matrix, 1), inside

    # one level pixel = 1 / PITCH_PX cells = CELL_DOTS / PITCH_PX dots
    moved = sample.read_rgb(world.crops, world.lfp,
                            offset_dots_xy=(CELL_DOTS / PITCH_PX, 0.0))
    assert moved.refusal is None
    pixels_0, rings_0, inside_0 = _features(world.read)
    pixels_1, rings_1, inside_1 = _features(moved)
    both = inside_0 & inside_1
    assert both.sum() > 1000

    def _relative(before, after):
        return float(np.linalg.norm(after[both] - before[both])
                     / np.linalg.norm(before[both]))

    shift_pixels = _relative(pixels_0, pixels_1)
    shift_rings = _relative(rings_0, rings_1)
    print(f"\none-pixel shift moves pixels by {shift_pixels:.4f} and rings "
          f"by {shift_rings:.4f} (relative L2)")
    assert shift_rings < shift_pixels

    # and it is the same machinery: `rings` is a mode, not a second filter
    score, detail = world.score(mode="rings")
    assert detail["patch_feature_kind"] == "rings"
    assert detail["patch_features"] == 6
    assert detail["patch_fitted_states"] == (0, 1, 3)
    same, _detail = world.score(
        spec=dc_replace(world.spec, features="rings"))
    assert np.array_equal(score, same, equal_nan=True)


def test_mixture_scores_state3_cells_only_and_refuses_small_populations(
        world, monkeypatch):
    score, detail = world.score(mode="mixture")
    state = (world.frame.bits[:, 1].astype(int)
             + 2 * world.frame.bits[:, 2].astype(int))
    three = np.flatnonzero(state == 3)
    assert detail["mixture_cells"] == three.size >= patch_mod.MIXTURE_MIN_CELLS
    assert detail["mixture_refused"] is None
    assert detail["patch_fallback_cells"] == world.cells.shape[0] - three.size
    assert detail["patch_feature_kind"] == "mixture"
    assert detail["patch_labels_from"] == "none"
    # the ink component is the DARK one, with no label to tell it so
    assert detail["mixture_mu"][0] < detail["mixture_mu"][1]
    target = world.frame.bits[:, 0] == 1
    assert d_prime(score[three], target[three]) > 0.5
    # every other cell is the fallback, on the shared scale
    others = np.flatnonzero(state != 3)
    expect = ((world.box_score()[others] - detail["patch_fallback_centre_value"])
              / detail["patch_fallback_scale"])
    assert np.allclose(score[others], expect)
    # a small population is refused, not segmented
    monkeypatch.setattr(patch_mod, "MIXTURE_MIN_CELLS", 10 ** 6)
    refused, refused_detail = world.score(mode="mixture")
    assert refused_detail["mixture_refused"] == "below_mixture_min_cells"
    assert refused_detail["patch_fallback_cells"] == world.cells.shape[0]
    assert np.isfinite(refused).all()


def test_patch_search_mode_patch_evaluates_the_grid_under_the_patch_objective_and_not_the_swim(
        world):
    """E2 in one place: the GRID follows `patch_search_mode`, the swim and
    the word pose never do (APPROACHES ruling 1), and the fits are counted
    because each candidate pose is an extraction AND a cross-fit."""
    common = dict(mix=world.mix, cell_dots=CELL_DOTS)
    searching = patch_mod.PatchSpec(search_mode="patch")
    _read, grid = arms.register("offset", world.lane, world.crops, world.lfp,
                                world.frame, 0, "patch", world.folds,
                                spec=searching, **common)
    assert grid["register_objective_mode"] == "patch"
    assert grid["patch_search_fits"] == grid["offset_evaluations"] > 20
    _read, plain = arms.register("offset", world.lane, world.crops, world.lfp,
                                 world.frame, 0, "patch", world.folds,
                                 spec=world.spec, **common)
    assert plain["register_objective_mode"] == "subtract"
    assert "patch_search_fits" not in plain
    assert plain["offset_evaluations"] == grid["offset_evaluations"]
    for arm in ("affine", "word", "committed"):
        _read, detail = arms.register(arm, world.lane, world.crops, world.lfp,
                                      world.frame, 0, "patch", world.folds,
                                      spec=searching, **common)
        assert detail["register_objective_mode"] == "subtract", arm
        assert "patch_search_fits" not in detail, arm


# --------------------------------------------- W8 B3: P1g, the local5 scope

class _FakeInputs:
    """Just enough `RunInputs` for the loader's bookkeeping."""

    def __init__(self, tiles_yx=(8, 8)):
        self._cache: dict = {}
        self.tiles_yx = tiles_yx
        self.row = None
        self.geometry = None


def _stub_harvest(seen: list, width: int = 144, origin_y: int | None = None):
    def harvest(inputs, certs, lane, page, tile_yx, forbidden, plane, axes):
        seen.append((lane.lane_id, tuple(tile_yx), forbidden))
        assert tuple(tile_yx) != forbidden
        assert set(axes) >= {"samples_per_cell", "window_cells", "channels",
                             "features"}
        rows = 700                                # over the 512 cap
        base = tile_yx[0] * 64 if origin_y is None else origin_y
        cells = np.stack((np.full(rows, base),
                          np.arange(rows)), axis=1).astype(np.int64)
        return (np.zeros((rows, width), np.float32),
                (np.arange(rows) % 2).astype(np.uint8),
                (np.arange(rows) % 4).astype(np.int8), cells,
                np.zeros(rows, bool))
    return harvest


def test_the_local5_harvest_drops_every_row_inside_the_target_footprint(
        world, monkeypatch):
    """DESIGN §4.8, one door further out (review 2026-09-06).

    A halo-48 footprint reaches deep into its neighbours, so a harvested
    neighbour cell can be one of the TARGET's own search- or select-fold
    cells — measured at ~11 % of the footprint's select fold on r0850
    geometry.  Every arm's `label_llr`, `select_arm`'s paired test and
    `platt`'s weights would then be partly in-sample.  The loader drops
    those rows at assembly, and says how many.
    """
    from analyzer import patchlocal

    inputs = _FakeInputs()
    monkeypatch.setattr("analyzer.frame._certs_token", lambda *a, **k: "tok")
    # every stub row sits on ONE page row, so the footprint below covers
    # a known, countable slice of them
    monkeypatch.setattr(patchlocal, "harvest_tile",
                        _stub_harvest([], origin_y=192))
    footprint = np.stack((np.full(50, 192), np.arange(100, 150)),
                         axis=1).astype(np.int64)
    labels, detail = patchlocal.local_patch_labels(
        inputs, {}, (0, 3, 4, "C"), world.lane, world.spec,
        footprint_cells_yx=footprint)
    # 24 tiles x 512 capped rows, all on row 192; the cap keeps whichever
    # of x in [0, 700) `fold_hash` ranks first, so the overlap count is
    # whatever it is — what must hold is that NONE survives
    assert detail["patch_local_rows_dropped_footprint"] > 0
    inside = ((labels.cells_yx[:, 0] == 192)
              & (labels.cells_yx[:, 1] >= 100)
              & (labels.cells_yx[:, 1] < 150))
    assert not np.any(inside), "a footprint cell trained the filter"
    assert labels.n_rows + detail["patch_local_rows_dropped_footprint"] == \
        24 * patchlocal.PATCH_LOCAL_MAX_ROWS_PER_TILE
    # ... and with no footprint named, nothing is dropped
    inputs2 = _FakeInputs()
    monkeypatch.setattr(patchlocal, "harvest_tile",
                        _stub_harvest([], origin_y=192))
    _all_rows, plain = patchlocal.local_patch_labels(
        inputs2, {}, (0, 3, 4, "C"), world.lane, world.spec)
    assert plain["patch_local_rows_dropped_footprint"] == 0


def test_a_chosen_geometry_slices_the_local5_harvest_instead_of_dropping_it(
        world):
    """The harvest is cut at the WALK's widest grid (review 2026-09-06).

    It used to be cut at the INHERITED one, so a population that chose
    any other width silently lost every neighbourhood label — and B7's
    own synthetic print has the coreless state 3 choosing window 2.0,
    the one choice that guaranteed the loss.  Cut wide, every candidate
    is a column slice and no choice can drop the rows.

    The rows here are the World's own halo cells extracted at the walk's
    geometry: `patch_score` cannot tell them from a neighbour tile's, and
    the claim under test is the geometry plumbing, not the provenance.
    """
    from analyzer.patchlocal import _GridSpec

    spec = _auto_spec()
    _inherited, auto_axes, walk, _refused = patch_mod.walk_geometry(spec,
                                                                   "patch")
    assert auto_axes and float(walk["window_cells"]) == 2.0
    rows = np.flatnonzero(~np.asarray(world.fp.in_tile, bool)
                          & np.asarray(world.lfp.observed, bool))
    pitch = float(world.crops.pitch_px_level)
    grid = patchgrid_mod.grid_cells(
        _GridSpec(int(walk["samples_per_cell"]), float(walk["window_cells"])),
        pitch)
    features, inside = patchgrid_mod.extract(
        world.crops, world.read.points_yx, world.read.linear_by_owner,
        world.lfp.owner_index, rows, grid, tuple(walk["channels"]))
    rows = rows[inside]
    assert rows.size > 500
    states = (world.frame.bits[:, 1].astype(np.int8)
              + 2 * world.frame.bits[:, 2].astype(np.int8))
    local = patch_mod.PatchLabels(
        features=np.asarray(features[inside], np.float32),
        bits=np.asarray(world.frame.bits[rows, 0], np.uint8),
        state=states[rows], cells_yx=world.cells[rows],
        word=np.zeros(rows.size, bool), n_tiles=1, axes=dict(walk))
    _score, detail = world.score(spec=spec, local_labels=local)
    assert detail["patch_local_refused"] is None
    used = sum(int(entry.get("n_local", 0))
               for entry in detail["patch_states"].values())
    dropped = sum(int(entry.get("n_local_dropped", 0))
                  for entry in detail["patch_states"].values())
    chosen = {tag: axes["window_cells"]
              for tag, axes in detail["auto_choices"].items()
              if "window_cells" in axes}
    print(f"\n  windows {chosen}, local rows used {used}, dropped {dropped}")
    assert set(chosen.values()) != {float(walk["window_cells"])}, \
        "the populations must not all have chosen the harvest geometry"
    assert used > 0 and dropped == 0


def test_local5_memo_is_per_lane_and_tile_row_capped_and_lru_bounded(
        world, monkeypatch):
    from analyzer import patchlocal

    inputs = _FakeInputs()
    monkeypatch.setattr("analyzer.frame._certs_token", lambda *a, **k: "tok")
    seen: list = []
    monkeypatch.setattr(patchlocal, "harvest_tile", _stub_harvest(seen))
    key = (0, 3, 4, "C")
    labels, detail = patchlocal.local_patch_labels(
        inputs, {}, key, world.lane, world.spec)
    assert detail["patch_local_tiles_offered"] == 24      # the 5x5, target out
    assert detail["patch_local_tiles_read"] == 24
    assert labels.n_tiles == 24
    assert labels.n_rows == 24 * patchlocal.PATCH_LOCAL_MAX_ROWS_PER_TILE

    # the memo key is (lane, stream, certs, page, TILE, spec, features) —
    # the target is NOT in it, so the next target re-uses every entry it
    # shares, and the target's own tile is never harvested
    store = inputs._cache["patch_local_labels"]
    assert len(store) == 24
    walk = patch_mod.walk_geometry(world.spec, "patch")[2]
    for cache_key in store:
        assert cache_key[0] == world.lane.lane_id
        assert cache_key[1] == "C" and cache_key[2] == "tok"
        assert cache_key[4] != (3, 4)
        # the WALK's widest geometry, not the spec's own (review
        # 2026-09-06): one harvest serves every candidate a population
        # may choose, so nothing is thrown away by a choice
        assert cache_key[5] == (int(walk["samples_per_cell"]),
                                float(walk["window_cells"]),
                                tuple(walk["channels"]), "pixels")
    before = len(seen)
    _again, again_detail = patchlocal.local_patch_labels(
        inputs, {}, (0, 3, 5, "C"), world.lane, world.spec)
    assert again_detail["patch_local_memo_hits"] >= 15    # the shared block
    assert len(seen) < before + 24

    # the LRU is bounded: 600 inserts leave 512 entries, newest kept
    for index in range(600):
        patchlocal._remember(store, ("x", index), index)
    assert len(store) == patchlocal.PATCH_LOCAL_MAX_ENTRIES
    assert ("x", 599) in store and ("x", 0) not in store

    # a mismatched feature width is REFUSED, never broadcast into a fit
    monkeypatch.setattr(patchlocal, "harvest_tile", _stub_harvest([], 7))
    inputs2 = _FakeInputs()
    narrow, _detail = patchlocal.local_patch_labels(
        inputs2, {}, key, world.lane, world.spec)
    _score, wide_detail = world.score(local_labels=narrow)
    assert wide_detail["patch_local_refused"].startswith("features 7 !=")
    assert wide_detail["patch_labels_from"] == "halo"


def test_local5_rows_join_the_fit_of_their_state_and_are_capped_deterministically(
        world):
    from analyzer import patchlocal

    cells = np.stack((np.full(900, 200), np.arange(900)), axis=1).astype(
        np.int64)
    rows = np.arange(900)
    first = patchlocal._capped(cells, rows)
    second = patchlocal._capped(cells, rows)
    assert first.size == patchlocal.PATCH_LOCAL_MAX_ROWS_PER_TILE
    assert np.array_equal(first, second)          # deterministic, no RNG
    assert np.array_equal(first, np.sort(first))

    # a labelled row from outside the footprint trains the state it names
    base, base_detail = world.score()
    ring = np.flatnonzero(~np.asarray(world.fp.in_tile, bool))
    grid = patch_mod.grid_cells(world.spec, PITCH_PX)
    features, inside = patch_mod.extract(
        world.crops, world.read.points_yx, world.read.linear_by_owner,
        world.lfp.owner_index, ring, grid, world.spec.channels)
    take = np.flatnonzero(inside)[:400]
    state = (world.frame.bits[:, 1].astype(np.int8)
             + 2 * world.frame.bits[:, 2].astype(np.int8))
    labels = patch_mod.PatchLabels(
        features=features[take],
        bits=np.asarray(world.frame.bits[ring[take], 0], np.uint8),
        state=state[ring[take]],
        cells_yx=world.cells[ring[take]] + np.int64(1000),
        word=np.zeros(take.size, bool), n_tiles=3)
    scored, detail = world.score(local_labels=labels)
    assert detail["patch_local_rows"] == 400 and detail["patch_local_tiles"] == 3
    assert detail["patch_labels_from"] == "halo+local5"
    assert sum(entry.get("n_local", 0)
               for entry in detail["patch_states"].values()) > 0
    assert not np.array_equal(base, scored, equal_nan=True)
    assert base_detail["patch_local_rows"] == 0

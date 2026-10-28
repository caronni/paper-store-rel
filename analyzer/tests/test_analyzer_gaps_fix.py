"""The three builds the GAPS-2026-09-03 measurement earned.

1. The starved-branch fallback (DESIGN §4.7 amended): the two-population
   split may never zero a tile.
2. The neighbourhood context `local5` (RULING 2026-09-03): a fitted model
   takes a 5x5-tile neighbourhood, shrunk toward the footprint's own fit
   by label count and gated on the footprint's own held-out labels.
3. The re-roll (GAPS §7): after the SELECTED arm's ladder fails, the
   remaining arms' already-computed evidence gets its own L0/L1.

Truth appears here only as the SCORE of a synthetic frame the test itself
built; nothing under test reads it.
"""

from __future__ import annotations

from dataclasses import replace as dc_replace

import numpy as np
import pytest

from holo3.lib import ldpc
from holo3.plugins import calibrate as calibrate_plugin

from analyzer import arms as arms_mod
from analyzer import calibrate as cal
from analyzer import combine as combine_mod
from analyzer import controls as ctl
from analyzer import fixedpoint as fp
from analyzer import frame as frame_mod
from analyzer.types import (AnalyzerConfig, Evidence, KnownFrame,
                            LaneFootprint, Ledger, LedgerRow, LocalContext,
                            TileFootprint, VERDICT_CERTIFIED)

from ._synthetic import R0850, build_frame, row_of
from .test_analyzer_gaps import _halo_clean_frame


# ------------------------------------------------- 1. the starved branch

def _score_for(frame, cells, *, seed: int = 11) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.asarray(frame.bits[:, 0], np.float64) + rng.normal(
        0.0, 0.3, cells.shape[0])


def test_the_default_prices_the_tile_the_split_used_to_erase():
    """DESIGN §4.7 amended: a starved branch is pooled, never erased."""
    frame, lfp, cells, in_tile = _halo_clean_frame()
    folds = cal.split_folds(cells, 4)
    llr, detail = cal.calibrate(_score_for(frame, cells), frame, 0, lfp,
                                folds, branches="subtract", ctx_mode="none")
    other = detail["branches"][cal.BRANCH_OTHER]
    assert not other["accepted"]              # the branch still refuses
    fallback = detail["branch_fallback"]
    assert fallback is not None and fallback["accepted"]
    assert fallback["n_cells"] == int(np.count_nonzero(in_tile))
    # ... and the tile is priced, not zeroed
    assert np.count_nonzero(llr[in_tile]) == int(np.count_nonzero(in_tile))
    agree = np.mean((llr[in_tile] > 0) == (frame.bits[in_tile, 0] > 0))
    assert agree > 0.9


def test_the_fallback_leaves_an_accepted_branch_exactly_alone():
    """It only ever fills what would have been zero."""
    frame, lfp, cells, _in_tile = _halo_clean_frame()
    folds = cal.split_folds(cells, 4)
    score = _score_for(frame, cells)
    off, _ = cal.calibrate(score, frame, 0, lfp, folds, branches="subtract",
                           ctx_mode="none", starved_fallback=False)
    on, detail = cal.calibrate(score, frame, 0, lfp, folds,
                               branches="subtract", ctx_mode="none",
                               starved_fallback=True)
    covered_before = off != 0.0
    assert np.array_equal(on[covered_before], off[covered_before])
    assert np.any(on[~covered_before] != 0.0)
    assert detail["n_calibrated"] > 0


def test_the_erasure_is_still_reachable_with_the_fallback_off():
    """The unamended §4.7 behaviour, so the amendment stays a CHOICE.

    Carries the assertion `test_analyzer_calibrate.py::
    test_calibrate_refuses_a_starved_branch_with_zero_llr` made about the
    old default: a branch below `pava`'s floors prices nothing.
    """
    frame, lfp, cells, in_tile = _halo_clean_frame()
    folds = cal.split_folds(cells, 4)
    llr, detail = cal.calibrate(_score_for(frame, cells), frame, 0, lfp,
                                folds, branches="subtract", ctx_mode="none",
                                starved_fallback=False)
    assert detail["branch_fallback"] is None
    assert np.all(llr[in_tile] == 0.0)
    assert np.any(llr[~in_tile] != 0.0)


def test_the_fallback_refuses_too_when_the_union_has_no_labels():
    """No labels anywhere is still a refusal, not a fabricated map."""
    frame, lfp, cells, in_tile = _halo_clean_frame()
    blind = dc_replace(frame, known=np.zeros_like(frame.known))
    folds = cal.split_folds(cells, 4)
    llr, detail = cal.calibrate(_score_for(frame, cells), blind, 0, lfp,
                                folds, branches="subtract", ctx_mode="none")
    assert detail["branch_fallback"]["accepted"] is False
    assert detail["branch_fallback"]["reason"] == "search_class_starved"
    assert np.all(llr == 0.0)
    del in_tile


# --------------------------------------------- 2. the local5 context

def _ctx_frame(n: int = 4000, *, seed: int = 3, bin_effect: bool = True):
    """A flat footprint with dense labels and a real per-bin effect."""
    rng = np.random.default_rng(seed)
    side = int(np.ceil(np.sqrt(n)))
    cells = np.stack(np.meshgrid(np.arange(side), np.arange(side),
                                 indexing="ij"), axis=-1).reshape(-1, 2)[:n]
    bins = (np.arange(n) % calibrate_plugin.N_CONTEXT_BINS).astype(np.int8)
    shift = (np.linspace(-1.5, 1.5, calibrate_plugin.N_CONTEXT_BINS)
             if bin_effect else
             np.zeros(calibrate_plugin.N_CONTEXT_BINS))
    probability = 1.0 / (1.0 + np.exp(-shift[bins]))
    values = (rng.random(n) < probability).astype(np.uint8)
    bits = np.zeros((n, 3), np.uint8)
    bits[:, 0] = values
    known = np.ones((n, 3), bool)
    frame = KnownFrame(
        bits=bits, known=known, furniture=np.zeros(n, bool),
        metadata_cell=None, regressors=known.all(axis=1),
        labels=known[:, 0], siblings=np.ones(n, bool), n_discriminating=0,
        furniture_kind=None, target=(0, 1, 1, "C"), detail={})
    footprint = TileFootprint(page=0, ty=1, tx=1, halo_cells=16,
                              page_cells_yx=cells,
                              in_tile=np.ones(n, bool),
                              cargo=np.ones(n, bool),
                              page_shape_cells_yx=(side, side))
    lfp = LaneFootprint(lane=("cap", 0), tile=footprint,
                        observed=np.ones(n, bool),
                        owner_index=np.zeros(n, np.int32),
                        points_yx=np.zeros((n, 2)))
    llr = np.zeros(n, np.float64)             # no context knowledge at all
    return frame, lfp, cells, bins, llr


def _local(offsets, bin_labels, *, adopted: bool = True) -> LocalContext:
    return LocalContext(
        lane=("cap", 0), page=0, stream_id="C", target_tile_yx=(1, 1),
        radius_tiles=2, offsets=tuple(float(v) for v in offsets),
        bin_labels=tuple(int(v) for v in bin_labels), adopted=bool(adopted),
        reason="adopted" if adopted else "validation_gate_failed",
        baseline_logloss=1.0, candidate_logloss=0.9,
        tiles=((0, 0),), n_tiles_read=1, n_fit_labels=1000,
        n_validation_labels=500)


def test_local5_shrinks_toward_the_footprint_by_label_count():
    frame, lfp, cells, bins, llr = _ctx_frame()
    folds = cal.split_folds(cells, 7)
    n_bins = calibrate_plugin.N_CONTEXT_BINS
    labels = np.zeros(n_bins, np.int64)
    labels[n_bins // 2:] = 10 ** 6            # the neighbourhood dominates
    local = _local(np.full(n_bins, 2.0), labels)
    _out, detail = cal._apply_local_context(
        llr, bins, frame, 0, folds, np.ones(llr.size, bool), local)
    weights = np.asarray(detail["ctx_blend_weights"], np.float64)
    assert weights.size == n_bins
    assert np.all(weights[:n_bins // 2] == 0.0)     # no neighbourhood labels
    assert np.all(weights[n_bins // 2:] > 0.99)     # ~all neighbourhood
    offsets = np.asarray(detail["ctx_offsets"], np.float64)
    if detail["ctx_blend_adopted"]:
        assert np.allclose(offsets[n_bins // 2:], 2.0, atol=1e-3)


def test_local5_applies_an_adopted_blend_and_says_so():
    frame, lfp, cells, bins, llr = _ctx_frame()
    folds = cal.split_folds(cells, 7)
    n_bins = calibrate_plugin.N_CONTEXT_BINS
    truth = np.linspace(-1.5, 1.5, n_bins)     # the effect the data has
    local = _local(truth, np.full(n_bins, 10 ** 6))
    out, detail = cal._apply_local_context(
        llr, bins, frame, 0, folds, np.ones(llr.size, bool), local)
    assert detail["ctx_adopted"] is True
    assert detail["ctx_reason"] == "local5_blend"
    assert np.allclose(np.asarray(detail["ctx_offsets"]), truth, atol=1e-3)
    assert np.allclose(out, np.clip(truth[bins.astype(np.int64)],
                                    -ldpc.LLR_CLIP, ldpc.LLR_CLIP),
                       atol=1e-3)


def test_local5_without_a_neighbourhood_is_exactly_production():
    frame, lfp, cells, _bins, _llr = _ctx_frame()
    folds = cal.split_folds(cells, 7)
    score = np.asarray(frame.bits[:, 0], np.float64) + \
        np.random.default_rng(2).normal(0.0, 0.5, cells.shape[0])
    production, left = cal.calibrate(score, frame, 0, lfp, folds,
                                     branches="pooled",
                                     ctx_mode="production")
    local, right = cal.calibrate(score, frame, 0, lfp, folds,
                                 branches="pooled", ctx_mode="local5",
                                 local_context=None)
    assert np.array_equal(production, local)
    assert left["ctx_adopted"] == right["ctx_adopted"]
    assert right["ctx_scope"] == "local5"
    assert right["ctx_local_reason"] == "no_local_context"


def test_local5_refuses_a_blend_that_loses_on_the_held_out_labels():
    frame, lfp, cells, bins, llr = _ctx_frame()
    folds = cal.split_folds(cells, 7)
    n_bins = calibrate_plugin.N_CONTEXT_BINS
    # offsets pointing the WRONG way, with every label behind them
    wrong = -np.linspace(-1.5, 1.5, n_bins) * 4.0
    local = _local(wrong, np.full(n_bins, 10 ** 6))
    out, detail = cal._apply_local_context(
        llr, bins, frame, 0, folds, np.ones(llr.size, bool), local)
    assert detail["ctx_blend_adopted"] is False
    assert detail["ctx_reason"].startswith("local5_refused")
    # what stands is the footprint's own correction, or nothing
    assert detail["ctx_adopted"] == detail["ctx_footprint_adopted"]
    if not detail["ctx_footprint_adopted"]:
        assert np.array_equal(out, llr)


def test_neighbourhood_tiles_excludes_the_target_and_clips_at_the_edge():
    class _Inputs:
        tiles_yx = (53, 37)

    interior = arms_mod.neighbourhood_tiles(_Inputs(), 10, 10, 2)
    assert len(interior) == 24
    assert (10, 10) not in interior
    assert min(y for y, _ in interior) == 8
    assert max(x for _, x in interior) == 12
    corner = arms_mod.neighbourhood_tiles(_Inputs(), 0, 0, 2)
    assert len(corner) == 8                    # a 3x3 block minus the target
    assert all(0 <= y < 53 and 0 <= x < 37 for y, x in corner)
    assert corner == tuple(sorted(corner))     # deterministic order


# ------------------------------------------------------- 3. the re-roll

def _ev(arm: str, lane, *, key=(0, 12, 7, "C"), n: int = 8) -> Evidence:
    return Evidence(key=key, lane=lane, arm=arm,
                    llr_sequential=np.zeros(n), observed=np.ones(n, bool),
                    blind={})


def test_reroll_sets_skips_what_the_selection_already_ran():
    lanes = [("cap-a", 0), ("cap-b", 0)]
    candidates = {lane: [_ev("subtract+offset", lane), _ev("head+offset",
                                                           lane)]
                  for lane in lanes}
    selected = [_ev("subtract+offset", lane) for lane in lanes]
    sets = combine_mod.reroll_sets(candidates, selected)
    assert [arm for arm, _items in sets] == ["head+offset"]
    assert len(sets[0][1]) == 2
    # deterministic
    assert sets == combine_mod.reroll_sets(candidates, selected)


def test_reroll_sets_offers_a_mixed_selection_every_pure_arm():
    lanes = [("cap-a", 0), ("cap-b", 0)]
    candidates = {lane: [_ev("subtract+offset", lane), _ev("head+offset",
                                                           lane)]
                  for lane in lanes}
    selected = [_ev("subtract+offset", lanes[0]), _ev("head+offset",
                                                      lanes[1])]
    sets = combine_mod.reroll_sets(candidates, selected)
    assert [arm for arm, _items in sets] == ["subtract+offset",
                                             "head+offset"]


def test_reroll_sets_keeps_an_arm_only_some_lanes_have():
    lanes = [("cap-a", 0), ("cap-b", 0)]
    candidates = {lanes[0]: [_ev("subtract+offset", lanes[0]),
                             _ev("subtract+word", lanes[0])],
                  lanes[1]: [_ev("subtract+offset", lanes[1])]}
    selected = [_ev("subtract+offset", lane) for lane in lanes]
    sets = combine_mod.reroll_sets(candidates, selected)
    assert [arm for arm, _items in sets] == ["subtract+word"]
    assert len(sets[0][1]) == 1


class _FakeLane:
    capture_id = "cap-a"
    level_index = 0
    lane_id = ("cap-a", 0)


class _FakeInputs:
    def __init__(self, row, geometry):
        self.row = row
        self.geometry = geometry
        self.plane_fields: dict = {}


def _reroll_world(monkeypatch, *, good_arm: str = "head+offset"):
    """One lane, two arms: the default is noise, `good_arm` is the frame."""
    built = build_frame(R0850, key=(0, 12, 7, "C"), seed=5)
    row = row_of(R0850)
    geometry = frame_mod.geometry_of(row)
    inputs = _FakeInputs(row, geometry)
    good = np.where(np.asarray(built.printed, np.uint8) > 0, 6.0, -6.0)
    noise = np.full(good.size, 0.0)

    def fake_lanes(_inputs, _page, _ty, _tx, cover_fraction=0.9):
        return [_FakeLane()]

    def fake_evidence(_inputs, _certs, key, lane, arm, *, halo_cells=None,
                      knobs=None):
        values = good if arm == good_arm else noise
        return Evidence(key=key, lane=lane.lane_id, arm=arm,
                        llr_sequential=np.asarray(values, np.float64),
                        observed=np.ones(values.size, bool),
                        blind={"arm": arm})

    monkeypatch.setattr(fp.sample_mod, "lanes_for_tile", fake_lanes)
    monkeypatch.setattr(fp.arms_mod, "evidence_for", fake_evidence)
    return inputs, built


def test_a_reroll_certifies_what_the_selected_arm_could_not(monkeypatch):
    inputs, built = _reroll_world(monkeypatch)
    config = AnalyzerConfig(arms=("subtract+offset", "head+offset"),
                            rules=("sum",), rungs=("L0",),
                            reroll=True, all_rules=False)
    out = fp.blind_key(inputs, {}, built.key, config, fp.shared_exposure())
    assert out.get("user_bits") is not None
    assert out["certifying_arm"] == "reroll:head+offset"
    assert out["certifying_rule"] == "sum|reroll:head+offset"
    assert out["reroll"]["arms"] == ["head+offset"]
    assert np.array_equal(np.asarray(out["user_bits"], np.uint8),
                          np.asarray(built.user, np.uint8))


def test_without_the_reroll_the_same_tile_stays_open(monkeypatch):
    inputs, built = _reroll_world(monkeypatch)
    config = AnalyzerConfig(arms=("subtract+offset", "head+offset"),
                            rules=("sum",), rungs=("L0",),
                            reroll=False, all_rules=False)
    out = fp.blind_key(inputs, {}, built.key, config, fp.shared_exposure())
    assert out.get("user_bits") is None
    assert "reroll" not in out


def test_the_selected_arm_still_names_itself_when_it_wins(monkeypatch):
    inputs, built = _reroll_world(monkeypatch, good_arm="subtract+offset")
    config = AnalyzerConfig(arms=("subtract+offset", "head+offset"),
                            rules=("sum",), rungs=("L0",),
                            reroll=True, all_rules=False)
    out = fp.blind_key(inputs, {}, built.key, config, fp.shared_exposure())
    assert out.get("user_bits") is not None
    assert out["certifying_arm"] == "subtract+offset"
    assert "reroll" not in out                 # nothing to re-roll: it won


class _NoCertificates:
    """A stand-in run: the parity check reads `certificates` and nothing
    else off `inputs` once `fp.run` is faked out."""

    certificates: dict = {}


def test_parity_sample_turns_the_reroll_off(monkeypatch):
    """A parity number measures ONE configuration's attempts (GAPS §7)."""
    seen: list = []

    def fake_run(_inputs, _targets, config, **_kwargs):
        seen.append(config)
        return Ledger(header={}, rows=[])

    monkeypatch.setattr(ctl.fp, "run", fake_run)
    rows = [LedgerRow(page=0, ty=ty, tx=0, stream_id="C", esi=ty,
                      covered=True, certified_by_production=True,
                      source="scan", band="live", band_any="live",
                      neighbours_certified=8, siblings_certified=("M",),
                      known_cells_in_halo=100, n_discriminating_labels=13,
                      production_attempts={}, metadata_known=True)
            for ty in range(4)]
    ctl.parity_sample(_NoCertificates(), rows, AnalyzerConfig(),
                      n_per_stream=2)
    assert seen and all(config.reroll is False for config in seen)
    assert AnalyzerConfig().reroll is True     # ... and ON everywhere else


def test_a_reroll_certificate_is_gated_like_any_other(monkeypatch):
    """Syndrome + CRC, and the exposure is charged (DESIGN §0)."""
    inputs, built = _reroll_world(monkeypatch)
    exposure = fp.shared_exposure()
    config = AnalyzerConfig(arms=("subtract+offset", "head+offset"),
                            rules=("sum",), rungs=("L0",),
                            reroll=True, all_rules=False)
    out = fp.blind_key(inputs, {}, built.key, config, exposure)
    assert exposure.distinct >= 1
    hit = [item for batch in out["rungs"].values() for item in batch
           if item.verdict == VERDICT_CERTIFIED]
    assert hit and all(item.syndrome_ok for item in hit)


@pytest.mark.parametrize("mode", cal.CTX_MODES)
def test_every_context_mode_is_still_dispatchable(mode):
    frame, lfp, cells, _bins, _llr = _ctx_frame()
    folds = cal.split_folds(cells, 7)
    score = np.asarray(frame.bits[:, 0], np.float64)
    llr, detail = cal.calibrate(score, frame, 0, lfp, folds,
                                branches="pooled", ctx_mode=mode)
    assert llr.size == cells.shape[0]
    assert detail["ctx_mode"] == mode
    assert np.all(np.abs(llr) <= ldpc.LLR_CLIP + 1e-9)


# ------------------------------- 4. the defaults, and what stayed a profile

def test_the_adopted_defaults_are_the_ones_that_passed_the_gate():
    assert cal.STARVED_FALLBACK is True
    assert cal.DEFAULT_BRANCHES == "pooled"
    # the halo did NOT move: `wide-halo` lost (0, 2, 5, C) on sheet H
    assert arms_mod.HALO_CELLS == {"C": 16, "M": 16, "Y": 32}


def test_the_wide_halo_is_reachable_only_by_name():
    from analyzer.types import PROFILES, with_profile
    assert "wide-halo" in PROFILES
    wide = with_profile(AnalyzerConfig(), "wide-halo")
    assert wide.halo_cells == {"C": 48, "M": 48, "Y": 32}
    assert wide.knobs_from == "profile:wide-halo"
    assert AnalyzerConfig().halo_cells is None       # ... and never by default


def test_a_profile_merges_knobs_instead_of_replacing_them():
    from analyzer.types import with_profile
    base = AnalyzerConfig(knobs={"seed": 5})
    split = with_profile(base, "split-branches")
    assert split.knobs["seed"] == 5
    assert split.knobs["branches"] == "subtract"
    assert split.knobs["starved_fallback"] is False
    with pytest.raises(KeyError):
        with_profile(base, "no-such-profile")

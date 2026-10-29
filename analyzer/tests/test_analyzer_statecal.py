"""W8 B2: the sibling state, and the four mechanisms keyed on it.

Synthetic only.  Truth never appears: every label here is a `KnownFrame`
bit the way the instrument would meet it, and the one place a "correct
answer" is used is as the SCORE of a permutation control, which is the
blind twin of MEASUREMENTS-2026-09-06 §5b's own control.

The stimulus is the measured one, in miniature: the target plane's score
is well separated in sibling states 0-2 and BOTH weaker and shifted in
state 3 (the M+Y pile, where the third toner layer has no dot core), so
one pooled PAVA map over the union is a map fitted on a mixture and
applied to another — DESIGN §4.7's blocker B12, one axis further in.
"""

from __future__ import annotations

import ast
import pathlib

import numpy as np
import pytest

from holo.receiver.format.identity import build_site_geometry
from holo.receiver.lib import ldpc, pava, spectral
from holo.receiver.plugins import calibrate as calibrate_plugin

from analyzer import calibrate as cal
from analyzer import combine as comb
from analyzer import ladder as L
from analyzer import statecal
from analyzer.types import (VERDICT_BELOW_FLOOR, VERDICT_REFUSED, Evidence,
                            Exposure, KnownFrame, LaneFootprint,
                            TileFootprint)

from ._synthetic import R0850, build_frame, channel_llr

PLANE_C = 0


# ------------------------------------------------------------- fixtures

def _cells(n: int) -> np.ndarray:
    side = int(np.ceil(np.sqrt(n)))
    grid = np.stack(np.meshgrid(np.arange(side), np.arange(side),
                                indexing="ij"), axis=-1).reshape(-1, 2)
    return grid[:n].astype(np.int64)


def _frame_of(bits: np.ndarray, known: np.ndarray, cells: np.ndarray, *,
              kind: np.ndarray | None = None, plane: int = PLANE_C,
              stream: str = "C"):
    """A `KnownFrame` + `LaneFootprint` pair over one synthetic window."""
    n = bits.shape[0]
    left, right = spectral.siblings_of(plane)
    side = int(cells[:, 0].max()) + 1
    fp = TileFootprint(page=0, ty=0, tx=0, halo_cells=0,
                       page_cells_yx=cells, in_tile=np.ones(n, bool),
                       cargo=np.ones(n, bool),
                       page_shape_cells_yx=(side, side))
    frame = KnownFrame(
        bits=bits, known=known,
        furniture=(np.zeros(n, bool) if kind is None
                   else np.asarray(kind, np.int8) >= 0),
        metadata_cell=None, regressors=known.all(axis=1),
        labels=known[:, plane], siblings=known[:, left] & known[:, right],
        n_discriminating=0, furniture_kind=kind,
        target=(0, 0, 0, stream), detail={})
    lfp = LaneFootprint(lane=("cap", 0), tile=fp, observed=np.ones(n, bool),
                        owner_index=np.zeros(n, np.int32),
                        points_yx=np.zeros((n, 2)))
    return frame, lfp


def _state_frame(n: int = 6000, seed: int = 17, *, plane: int = PLANE_C,
                 unknown_fraction: float = 0.15,
                 word_fraction: float = 0.10, dust_fraction: float = 0.02):
    """A window with word/dust furniture and the word law in the bits.

    At a word site C == M and Y == 0 (`color_model.reference_states`), so
    for C every word row lands in sibling state 0 with C = 0 or state 1
    with C = 1 — the degeneracy ruling 11 excludes from a per-state fit.
    """
    rng = np.random.default_rng(seed)
    cells = _cells(n)
    bits = rng.integers(0, 2, (n, 3), dtype=np.uint8)
    kind = np.full(n, -1, np.int8)
    draw = rng.random(n)
    kind[draw < word_fraction] = statecal.FURNITURE_WORD
    kind[(draw >= word_fraction)
         & (draw < word_fraction + dust_fraction)] = statecal.FURNITURE_DUST
    word = kind == statecal.FURNITURE_WORD
    bits[word, 1] = bits[word, 0]
    bits[word, 2] = 0
    left, right = spectral.siblings_of(plane)
    known = np.zeros((n, 3), bool)
    proven = rng.random(n) >= unknown_fraction
    known[proven, left] = True
    known[proven, right] = True
    known[rng.random(n) < 0.55, plane] = True
    known[kind >= 0] = True                    # furniture is fully known
    return _frame_of(bits, known, cells, kind=kind, plane=plane)


#: The measured shape, in miniature: states 0-2 read well and state 3
#: (both siblings inked) reads weakly AND at a different level, which is
#: what makes one pooled map wrong for both populations.
_AMPLITUDE = np.array([1.6, 1.5, 1.5, 0.55])
_LEVEL = np.array([0.0, 1.1, -0.9, 2.6])
_NOISE = np.array([0.35, 0.35, 0.35, 0.50])


def _state_score(frame, plane: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    state = statecal.sibling_state(frame, plane)
    index = np.where(state >= 0, state, 0).astype(np.int64)
    signal = 2.0 * frame.bits[:, plane].astype(np.float64) - 1.0
    amplitude = np.where(state >= 0, _AMPLITUDE[index], 1.2)
    level = np.where(state >= 0, _LEVEL[index], 0.0)
    noise = np.where(state >= 0, _NOISE[index], 0.4)
    return signal * amplitude + level + rng.normal(0.0, 1.0, signal.size) \
        * noise


# ------------------------------------------------------- the convention

def test_sibling_state_convention_is_left_plus_two_right_ascending_minus_one_unknown():
    """`s = bits[left] + 2*bits[right]`, siblings ASCENDING, −1 unproven."""
    cells = _cells(8)
    bits = np.array([[0, 0, 0], [0, 1, 0], [0, 0, 1], [0, 1, 1],
                     [1, 0, 0], [1, 1, 0], [1, 0, 1], [1, 1, 1]], np.uint8)
    known = np.ones((8, 3), bool)
    known[5, 2] = False                       # one sibling unproven
    frame, _lfp = _frame_of(bits, known, cells)
    state = statecal.sibling_state(frame, PLANE_C)
    assert state.dtype == np.int8
    # C's siblings are (M, Y) ascending: M is the low bit, Y the high one.
    assert list(state) == [0, 1, 2, 3, 0, statecal.STATE_UNKNOWN, 2, 3]
    # M's siblings are (C, Y): C low, Y high — and row 5's Y is the
    # unproven one, so M loses that row too.
    assert list(statecal.sibling_state(frame, 1)) == [
        0, 0, 2, 2, 1, statecal.STATE_UNKNOWN, 3, 3]
    # Y's siblings are (C, M): C low, M high.
    assert list(statecal.sibling_state(frame, 2)) == [0, 2, 0, 2,
                                                      1, 3, 1, 3]


def test_statecal_imports_neither_calibrate_nor_combine():
    """The import-direction ruling: they dispatch INTO this module."""
    path = pathlib.Path(statecal.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    relative: set[str] = set()
    absolute: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            head = node.module or ""
            (relative if node.level else absolute).add(head)
        elif isinstance(node, ast.Import):
            absolute.update(alias.name for alias in node.names)
    # ONE analyzer module, and it is the value module both sides share.
    assert relative == {"types"}, relative
    assert not any(name.startswith("analyzer") for name in absolute), \
        absolute


# -------------------------------------------------------- C1: branches

def test_state_branches_fit_one_map_per_state_with_own_standardisation():
    frame, lfp = _state_frame()
    folds = cal.split_folds(lfp.tile.page_cells_yx, 4)
    score = _state_score(frame, PLANE_C, 31)
    llr, detail = cal.calibrate(score, frame, PLANE_C, lfp, folds,
                               branches=statecal.BRANCH_STATE)
    assert set(detail["branches"]) == set(statecal.STATE_BRANCHES) | {
        cal.BRANCH_OTHER}
    assert all(entry["accepted"] for entry in detail["branches"].values())
    assert np.all(np.abs(llr) <= ldpc.LLR_CLIP + 1e-9)

    pooled_llr, pooled_detail = cal.calibrate(score, frame, PLANE_C, lfp,
                                              folds, branches="pooled")
    assert set(pooled_detail["branches"]) == {cal.BRANCH_ALL}
    # The point of a map per state: held out, the states beat the mixture.
    assert detail["heldout_logloss_search"] < \
        pooled_detail["heldout_logloss_search"]

    # OWN STANDARDISATION, observably: under the pooled map the LLR is one
    # monotone function of the score, so two cells with the same score get
    # the same LLR.  Under the state branches they do not — s3's own
    # median and MAD put its cells on a different footing.
    state = statecal.sibling_state(frame, PLANE_C)
    left = np.flatnonzero(state == 0)
    right = np.flatnonzero(state == 3)
    partner = left[np.argmin(np.abs(score[right][:, None]
                                    - score[left][None, :]), axis=1)]
    close = np.abs(score[right] - score[partner]) < 1e-3
    assert np.any(close), "no comparable pair of cells"
    assert np.max(np.abs(llr[right[close]] - llr[partner[close]])) > 1.0
    assert np.max(np.abs(pooled_llr[right[close]]
                         - pooled_llr[partner[close]])) < 0.01


def test_state_fit_masks_exclude_word_sites_keep_dust_and_a_word_only_class_is_refused():
    frame, lfp = _state_frame()
    usable = np.ones(frame.bits.shape[0], bool)
    scoring = statecal.state_branch_masks(frame, PLANE_C, usable)
    training = statecal.state_fit_masks(frame, PLANE_C, usable)
    word = np.asarray(frame.furniture_kind, np.int8) == \
        statecal.FURNITURE_WORD
    dust = np.asarray(frame.furniture_kind, np.int8) == \
        statecal.FURNITURE_DUST
    for name in statecal.STATE_BRANCHES:
        assert not np.any(training[name] & word), name
        assert np.array_equal(training[name], scoring[name] & ~word)
        # dust survives: it is the only furniture that discriminates
        assert np.count_nonzero(training[name] & dust) == \
            np.count_nonzero(scoring[name] & dust)
    # `other` is untouched — it has no per-state degeneracy to protect.
    assert np.array_equal(training[cal.BRANCH_OTHER],
                          scoring[cal.BRANCH_OTHER])
    # and the switch really is a switch
    kept = statecal.state_fit_masks(frame, PLANE_C, usable,
                                    exclude_word_sites=False)
    assert np.array_equal(kept["s0"], scoring["s0"])

    # A state whose only labels are word sites is one-sided by
    # construction and must REFUSE, not fit a constant.
    n = frame.bits.shape[0]
    bits = np.array(frame.bits, copy=True)
    known = np.array(frame.known, copy=True)
    kind = np.array(frame.furniture_kind, copy=True)
    state = statecal.sibling_state(frame, PLANE_C)
    only_word = state == 2
    kind[only_word] = statecal.FURNITURE_WORD
    known[only_word, PLANE_C] = True
    bits[only_word, PLANE_C] = 1               # one class, as a word site
    frame2, lfp2 = _frame_of(bits, known, lfp.tile.page_cells_yx, kind=kind)
    folds = cal.split_folds(lfp2.tile.page_cells_yx, 4)
    _llr, detail = cal.calibrate(np.zeros(n) + _state_score(frame2, PLANE_C,
                                                            5),
                                 frame2, PLANE_C, lfp2, folds,
                                 branches=statecal.BRANCH_STATE)
    assert detail["branches"]["s2"]["accepted"] is False
    assert detail["branches"]["s2"]["reason"] == "search_class_starved"
    assert detail["branches"]["s2"]["n_fit_word"] == 0
    assert detail["branches"]["s0"]["n_fit_word"] == 0
    assert detail["branches"]["s0"]["n_fit_dust"] >= 0
    assert detail["branches"]["s0"]["n_fit_cargo"] > 0


def test_a_starved_state_is_priced_by_the_pooled_map_and_recorded():
    """DESIGN §4.7 AMENDED: a branch that cannot fit is never erased."""
    frame, lfp = _state_frame(n=4000, seed=23)
    n = frame.bits.shape[0]
    known = np.array(frame.known, copy=True)
    state = statecal.sibling_state(frame, PLANE_C)
    starved = np.flatnonzero(state == 3)
    known[starved, PLANE_C] = False            # no labels left in s3
    frame2, lfp2 = _frame_of(np.array(frame.bits), known,
                             lfp.tile.page_cells_yx,
                             kind=np.array(frame.furniture_kind))
    folds = cal.split_folds(lfp2.tile.page_cells_yx, 4)
    score = _state_score(frame2, PLANE_C, 77)
    llr, detail = cal.calibrate(score, frame2, PLANE_C, lfp2, folds,
                                branches=statecal.BRANCH_STATE)
    assert detail["branches"]["s3"]["accepted"] is False
    assert detail["branches"]["s3"]["n_fit_0"] == 0
    assert detail["branch_fallback"] is not None
    assert detail["branch_fallback"]["accepted"] is True
    # the erasure §4.7 would have made is exactly what the fallback filled
    assert np.count_nonzero(llr[starved] != 0.0) > 0.5 * starved.size
    assert detail["n_calibrated"] == n


def test_covered_cells_agrees_with_calibrate_under_state_branches():
    frame, lfp = _state_frame(n=4000, seed=29)
    known = np.array(frame.known, copy=True)
    state = statecal.sibling_state(frame, PLANE_C)
    known[state == 2, PLANE_C] = False
    frame2, lfp2 = _frame_of(np.array(frame.bits), known,
                             lfp.tile.page_cells_yx,
                             kind=np.array(frame.furniture_kind))
    folds = cal.split_folds(lfp2.tile.page_cells_yx, 4)
    score = _state_score(frame2, PLANE_C, 41)
    llr, detail = cal.calibrate(score, frame2, PLANE_C, lfp2, folds,
                                branches=statecal.BRANCH_STATE,
                                starved_fallback=False)
    covered = cal.covered_cells(frame2, PLANE_C, statecal.BRANCH_STATE,
                                lfp2, score, detail)
    assert int(np.count_nonzero(covered)) == detail["n_calibrated"]
    assert np.all(llr[~covered] == 0.0)


def test_calibrate_publishes_label_state_on_the_select_fold():
    frame, lfp = _state_frame()
    folds = cal.split_folds(lfp.tile.page_cells_yx, 4)
    score = _state_score(frame, PLANE_C, 13)
    _llr, detail = cal.calibrate(score, frame, PLANE_C, lfp, folds,
                                 branches=statecal.BRANCH_STATE)
    rows = detail["label_rows"]
    published = detail["label_state"]
    assert published.dtype == np.int8 and published.size == rows.size
    assert np.array_equal(published,
                          statecal.sibling_state(frame, PLANE_C)[rows])
    # it is a SELECT-fold view, like every other label_* array
    assert np.all(folds.select[rows])


def test_shuffled_fit_labels_take_the_per_state_maps_back_to_the_ordering():
    """Permutation control 1: everything the LABELS bought must vanish.

    Only the FIT-fold labels are shuffled, so the held-out labels the log
    loss is measured on stay honest.  What is left is NOT chance
    (log 2 = 0.693) and should not be asserted to be: isotonic
    regression's end blocks are the min prefix mean and the max suffix
    mean, which drift toward 0 and 1 even on random labels, so a PAVA map
    still reads the SCORE ORDER.  What must vanish is the rest — measured
    here as a held-out loss more than 4x the honest one.
    """
    frame, lfp = _state_frame(n=8000, seed=61)
    folds = cal.split_folds(lfp.tile.page_cells_yx, 4)
    score = _state_score(frame, PLANE_C, 19)
    _llr, honest = cal.calibrate(score, frame, PLANE_C, lfp, folds,
                                 branches=statecal.BRANCH_STATE)
    assert honest["heldout_logloss_search"] < 0.20

    bits = np.array(frame.bits, copy=True)
    fit_rows = np.flatnonzero(folds.fit & frame.known[:, PLANE_C])
    shuffled = np.random.default_rng(5).permutation(bits[fit_rows, PLANE_C])
    bits[fit_rows, PLANE_C] = shuffled
    frame2, lfp2 = _frame_of(bits, np.array(frame.known),
                             lfp.tile.page_cells_yx,
                             kind=np.array(frame.furniture_kind))
    _llr2, control = cal.calibrate(score, frame2, PLANE_C, lfp2, folds,
                                   branches=statecal.BRANCH_STATE)
    assert all(entry["accepted"] for entry in control["branches"].values())
    assert control["heldout_logloss_search"] > 0.45
    assert control["heldout_logloss_search"] > \
        4.0 * honest["heldout_logloss_search"]


# --------------------------------------------------- C2: state x context

def _context_world(n: int, seed: int, *, bias: float = 4.0,
                   plane: int = PLANE_C):
    """An LLR that is systematically too POSITIVE for state 3 at high bins."""
    rng = np.random.default_rng(seed)
    cells = _cells(n)
    bits = rng.integers(0, 2, (n, 3), dtype=np.uint8)
    known = np.ones((n, 3), bool)
    known[rng.random(n) < 0.4, plane] = False
    frame, lfp = _frame_of(bits, known, cells, plane=plane)
    state = statecal.sibling_state(frame, plane)
    bins = rng.integers(0, calibrate_plugin.N_CONTEXT_BINS, n).astype(np.int8)
    signal = 2.0 * bits[:, plane].astype(np.float64) - 1.0
    llr = 2.5 * signal + rng.normal(0.0, 0.8, n)
    llr = llr + bias * ((state == 3) & (bins >= 5))
    return frame, lfp, state, bins, llr


def test_state_context_keeps_the_pooled_nine_vector_under_ctx_offsets():
    frame, lfp, state, bins, llr = _context_world(4000, 3)
    folds = cal.split_folds(lfp.tile.page_cells_yx, 4)
    usable = np.ones(llr.size, bool)
    # a cell already at the LLR clip, in the state that will be corrected
    high = np.flatnonzero((state == 3) & (bins >= 5))[0]
    quiet = np.flatnonzero((state == 0) & (bins >= 5))[0]
    llr = np.array(llr, copy=True)
    llr[high] = ldpc.LLR_CLIP
    llr[quiet] = ldpc.LLR_CLIP

    out, detail = statecal.apply_state_context(llr, bins, state, frame,
                                               PLANE_C, folds, usable)
    assert detail["ctx_state_any_adopted"] is True
    assert detail["ctx_state_adopted"][3] is True
    offsets = detail["ctx_offsets_by_state"]
    assert len(offsets) == statecal.N_STATES
    assert len(offsets[3]) == calibrate_plugin.N_CONTEXT_BINS
    assert np.all(np.diff(np.asarray(offsets[3])) <= 1e-12)   # non-increasing
    # a state that refused moved NOTHING; a state that adopted moved only
    # its own cells, and only the ones that have a bin
    for index in range(statecal.N_STATES):
        mine = state == index
        if detail["ctx_state_adopted"][index]:
            assert np.array_equal(out[mine & (bins < 0)], llr[mine
                                                              & (bins < 0)])
        else:
            assert np.array_equal(out[mine], llr[mine])
            assert offsets[index] is None
    assert np.all(state[np.flatnonzero(out != llr)] >= 0)
    # THE DOCUMENTED CLAMP: an adopted state is re-clamped from 20 to 12
    assert detail["ctx_state_adopted"][0] is False, "the control state"
    assert out[high] <= pava.CTX_LLR_CLAMP + 1e-9
    assert out[quiet] == pytest.approx(ldpc.LLR_CLIP)

    # end to end: the pooled 9-vector and verdict are untouched, so
    # `pooled_ctx_offsets` still accepts the row.
    score = 2.0 * frame.bits[:, PLANE_C].astype(np.float64) - 1.0 \
        + np.random.default_rng(2).normal(0.0, 0.6, llr.size)
    _llr, cdetail = cal.calibrate(score, frame, PLANE_C, lfp, folds,
                                  branches=statecal.BRANCH_STATE,
                                  ctx_mode="production", ctx_state=True)
    assert len(cdetail["ctx_offsets"]) == calibrate_plugin.N_CONTEXT_BINS
    assert "ctx_state_any_adopted" in cdetail
    lane = Evidence(key=(0, 0, 0, "C"), lane=("aaaaaaaaaaaa", 3),
                    arm="subtract+offset",
                    llr_sequential=np.zeros(4), observed=np.ones(4, bool),
                    blind={"ctx_adopted": True,
                           "ctx_offsets": cdetail["ctx_offsets"]})
    pooled, pdetail = comb.pooled_ctx_offsets((lane,), np.ones(1))
    if cdetail["ctx_adopted"]:
        assert pooled is not None and pooled.size == \
            calibrate_plugin.N_CONTEXT_BINS
        assert "ctx_refused" not in pdetail


def test_state_context_refuses_per_state_below_the_production_floors_and_says_so():
    frame, lfp, state, bins, llr = _context_world(240, 11)
    folds = cal.split_folds(lfp.tile.page_cells_yx, 4)
    out, detail = statecal.apply_state_context(
        llr, bins, state, frame, PLANE_C, folds, np.ones(llr.size, bool))
    assert detail["ctx_state_any_adopted"] is False
    assert not any(detail["ctx_state_adopted"])
    assert all(offset is None for offset in detail["ctx_offsets_by_state"])
    assert all(reason in ("insufficient_search_support",
                          "search_class_starved",
                          "insufficient_validation_support",
                          "validation_class_starved")
               for reason in detail["ctx_state_reason"])
    assert np.array_equal(out, llr)            # nothing was applied


def _state3_offsets(bias: float, seed: int, *, shuffle: bool = False):
    frame, lfp, state, bins, llr = _context_world(4000, seed, bias=bias)
    folds = cal.split_folds(lfp.tile.page_cells_yx, 4)
    if shuffle:
        bits = np.array(frame.bits, copy=True)
        rows = np.flatnonzero(frame.known[:, PLANE_C])
        bits[rows, PLANE_C] = np.random.default_rng(88).permutation(
            bits[rows, PLANE_C])
        frame, _lfp = _frame_of(bits, np.array(frame.known),
                                lfp.tile.page_cells_yx)
    _out, detail = statecal.apply_state_context(
        llr, bins, state, frame, PLANE_C, folds, np.ones(llr.size, bool))
    return detail


def test_a_state_context_is_a_recalibration_and_invents_nothing_on_a_clean_channel():
    """MEASURED, and worth writing down: shuffling the LABELS does not
    disarm this arm, because the thing it corrects lives in the LLR.

    A 9-bin context offset is a RECALIBRATION — "cells in an inky
    neighbourhood are over-confident by this much" — so on a channel with
    a real bias the fit finds it whether or not the labels mean anything
    (measured here: −3.8 honest, −3.0 with the labels permuted).  The
    control that DOES bite is the other direction: on a channel with
    nothing to correct, the arm must not manufacture a correction, and
    production's validation gate is what stops it.  It is a strict `<` on
    a finite fold, so a chance adoption is possible and asserting "never
    adopted" would be asserting something false; what is bounded is the
    SIZE of anything it adopts.
    """
    biased = _state3_offsets(4.0, 3)
    assert biased["ctx_state_adopted"][3] is True
    assert min(biased["ctx_offsets_by_state"][3][5:]) < -2.0

    permuted = _state3_offsets(4.0, 3, shuffle=True)
    assert min(permuted["ctx_offsets_by_state"][3][5:]) < -2.0

    for seed in (3, 5, 9, 12):
        clean = _state3_offsets(0.0, seed)
        for offsets in clean["ctx_offsets_by_state"]:
            if offsets is not None:
                assert float(np.max(np.abs(offsets))) < 1.0, (seed, offsets)


def test_l3_refuses_when_a_state_context_was_adopted():
    """Ruling 10: the APPLY mode is exact for a POOLED correction only."""
    frame = build_frame(R0850)
    llr = channel_llr(frame.printed, 0.08, seed=303)
    offsets = tuple(np.linspace(1.0, -1.0, calibrate_plugin.N_CONTEXT_BINS))
    exposure = Exposure()
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L3",),
                           knobs={"ctx_offsets": offsets,
                                  "ctx_state_adopted": True, "iters": 30},
                           exposure=exposure, metadata_bit=None)
    assert [item.rung for item in results] == ["L3"]
    assert results[0].verdict == VERDICT_REFUSED
    assert results[0].detail["reason"] == "state_context_adopted"
    assert exposure.distinct == 0              # nothing was decoded
    # ...and without the flag the rung runs exactly as before
    ran = L.run_ladder(llr, frame.row, frame.key, rungs=("L3",),
                       knobs={"ctx_offsets": offsets, "iters": 30,
                              "rounds": 1},
                       exposure=Exposure(), metadata_bit=None)
    assert ran[0].detail.get("reason") != "state_context_adopted"


# ----------------------------------------------------- D1: `platt-state`

KEY = (0, 5, 6, "C")


def _lane(capture: str, llr_seq: np.ndarray, rows, label_llr, values, state,
          *, discriminating=None) -> Evidence:
    n = len(rows)
    blind = {
        "label_rows": np.asarray(rows, np.int64),
        "label_llr": np.asarray(label_llr, np.float64),
        "label_values": np.asarray(values, np.uint8),
        "label_discriminating": (np.ones(n, bool) if discriminating is None
                                 else np.asarray(discriminating, bool)),
        "label_state": np.asarray(state, np.int8),
        "heldout_logloss_select": 0.5}
    return Evidence(key=KEY, lane=(capture, 3), arm="subtract+offset",
                    llr_sequential=np.asarray(llr_seq, np.float64),
                    observed=np.ones(llr_seq.size, bool), blind=blind)


def _two_lane_world(n_cells: int = 200, seed: int = 7):
    """Lane A carries state 3, lane B carries state 0 — and only those."""
    rng = np.random.default_rng(seed)
    n_labels = 300
    rows = np.arange(n_labels, dtype=np.int64)
    values = rng.integers(0, 2, n_labels, dtype=np.uint8)
    signal = 2.0 * values.astype(np.float64) - 1.0
    label_state = np.array([3] * 150 + [0] * 150, np.int8)
    strong = np.where(label_state == 3, 3.0, 0.15)
    weak = np.where(label_state == 3, 0.15, 3.0)
    seq_state = np.full(n_cells, np.int8(-1), np.int8)
    seq_state[:100] = 3
    seq_state[100:180] = 0
    lane_a = _lane("aaaaaaaaaaaa", rng.normal(0.0, 1.0, n_cells), rows,
                   strong * signal + rng.normal(0.0, 1.0, n_labels),
                   values, label_state)
    lane_b = _lane("bbbbbbbbbbbb", rng.normal(0.0, 1.0, n_cells), rows,
                   weak * signal + rng.normal(0.0, 1.0, n_labels),
                   values, label_state)
    return (lane_a, lane_b), seq_state


def test_platt_state_floor_is_the_states_own_minority_not_the_discriminating_count():
    """Within a state the discriminating flag is DEGENERATE (see §4.0)."""
    rng = np.random.default_rng(3)
    state = np.array([3] * 120 + [0] * 120, np.int8)
    values = np.concatenate((np.tile([1, 0], 60), np.tile([1, 0], 60))
                            ).astype(np.uint8)
    # every discriminating label of state 3 carries the SAME target bit —
    # for C, "discriminating" is C != M, so with M fixed it must.
    discriminating = (state == 3) & (values == 1)
    assert cal._minority_count(values[discriminating]) == 0
    stack = np.stack([2.0 * (2.0 * values - 1.0)
                      + rng.normal(0.0, 1.0, values.size),
                      0.5 * (2.0 * values - 1.0)
                      + rng.normal(0.0, 1.0, values.size)])
    pooled, by_state, detail = statecal.state_platt_weights(
        stack, values, state, pooled_fit=comb._platt_weights)
    assert pooled.size == 2
    # 60 of each class in each of states 0 and 3 clears the floor of 40
    assert set(by_state) == {0, 3}
    assert detail["platt_state_counts"]["3"] == (60, 60)
    assert detail["platt_state_refused"] == {"1": "state_class_starved",
                                             "2": "state_class_starved"}

    # a state under the floor takes the pooled vector and says why
    thin = np.array([3] * 60 + [0] * 180, np.int8)
    _pooled, thin_by_state, thin_detail = statecal.state_platt_weights(
        stack, values, thin, pooled_fit=comb._platt_weights)
    assert 3 not in (thin_by_state or {})
    assert thin_detail["platt_state_refused"]["3"] == "state_class_starved"


def test_shuffled_select_labels_collapse_the_per_state_platt_weights():
    """Permutation control 3: with no signal, every weight goes to zero.

    `_platt_weights` minimises the select-fold log loss over w >= 0, so a
    lane that carries nothing is worth nothing — the optimum is w = 0 and
    the combination is the constant-1/2 predictor, which is exactly what
    a rule fitted on noise must do.
    """
    rng = np.random.default_rng(4)
    state = np.array([3] * 150 + [0] * 150, np.int8)
    values = rng.integers(0, 2, 300, dtype=np.uint8)
    signal = 2.0 * values.astype(np.float64) - 1.0
    stack = np.stack([3.0 * signal + rng.normal(0.0, 1.0, values.size),
                      1.0 * signal + rng.normal(0.0, 1.0, values.size)])
    honest, honest_by_state, _detail = statecal.state_platt_weights(
        stack, values, state, pooled_fit=comb._platt_weights)
    assert float(np.max(honest)) > 0.3
    assert set(honest_by_state) == {0, 3}

    shuffled = rng.permutation(values)
    pooled, by_state, detail = statecal.state_platt_weights(
        stack, shuffled, state, pooled_fit=comb._platt_weights)
    assert float(np.max(pooled)) < 0.05
    for weights in (by_state or {}).values():
        assert float(np.max(weights)) < 0.05
    assert detail["platt_state_counts"]["3"][0] > 0


def test_platt_state_applies_per_state_weights_and_pooled_elsewhere_and_publishes_both():
    lanes, seq_state = _two_lane_world()
    result = comb.combine(lanes, "platt-state", sibling_state=seq_state)
    assert result.rule == "platt-state"
    by_state = result.coefficients_by_state
    assert by_state is not None and len(by_state) == statecal.N_STATES
    assert by_state[1] is None and by_state[2] is None
    assert by_state[3] is not None and by_state[0] is not None
    # lane A is what state 3 is worth, lane B what state 0 is worth
    assert by_state[3][0] > by_state[3][1]
    assert by_state[0][1] > by_state[0][0]

    stack = np.stack([item.llr_sequential for item in lanes])
    pooled = np.asarray(result.coefficients, np.float64)
    for index in (0, 3):
        rows = seq_state == index
        weights = np.asarray(by_state[index], np.float64)
        assert np.allclose(result.llr_sequential[rows],
                           weights @ stack[:, rows])
    unknown = seq_state < 0
    assert np.allclose(result.llr_sequential[unknown],
                       pooled @ stack[:, unknown])
    # the POOLED vector is what `Combined.coefficients` publishes, so
    # `pooled_ctx_offsets` and every reader of the scale are unchanged
    plain = comb.combine(lanes, "platt")
    assert np.allclose(pooled, np.asarray(plain.coefficients, np.float64))
    summary = comb.combine_detail(result)
    assert summary["coefficients"] == result.coefficients
    assert summary["coefficients_by_state"] == by_state
    assert summary["ctx_state_adopted"] is False


def test_platt_state_without_a_sequential_state_falls_back_to_platt():
    lanes, seq_state = _two_lane_world()
    result = comb.combine(lanes, "platt-state")
    plain = comb.combine(lanes, "platt")
    assert result.coefficients_by_state is None
    assert np.allclose(result.llr_sequential, plain.llr_sequential)
    # a wrong-length vector is a driver bug, refused the same way
    short = comb.combine(lanes, "platt-state", sibling_state=seq_state[:5])
    assert short.coefficients_by_state is None
    assert np.allclose(short.llr_sequential, plain.llr_sequential)


def test_platt_state_refuses_to_the_pooled_rule_when_platt_itself_refuses():
    lanes, seq_state = _two_lane_world()
    thin = tuple(
        Evidence(key=item.key, lane=item.lane, arm=item.arm,
                 llr_sequential=item.llr_sequential, observed=item.observed,
                 blind={**item.blind,
                        "label_discriminating": np.zeros(
                            item.blind["label_rows"].size, bool)})
        for item in lanes)
    result = comb.combine(thin, "platt-state", sibling_state=seq_state)
    assert result.coefficients_by_state is None
    assert np.allclose(result.coefficients, 1.0)          # `sum`
    assert np.allclose(result.llr_sequential,
                       comb.combine(thin, "sum").llr_sequential)


def test_contributing_captures_is_the_union_over_pooled_and_state_supports():
    """A lane the pooled fit zeroed still contributes where a state uses it."""
    detail = {"lanes": (("aaaaaaaaaaaa", 3), ("bbbbbbbbbbbb", 3)),
              "coefficients": (0.0, 1.4),
              "coefficients_by_state": (None, None, None, (0.9, 0.0))}
    assert comb.contributing_captures(detail) == frozenset(
        {"aaaaaaaaaaaa", "bbbbbbbbbbbb"})
    # without the state vectors it is the pooled support alone (unchanged)
    assert comb.contributing_captures(
        {**detail, "coefficients_by_state": None}) == frozenset(
            {"bbbbbbbbbbbb"})


def test_a_state_context_in_a_contributing_lane_reaches_the_combination():
    lanes, seq_state = _two_lane_world()
    flagged = (Evidence(key=lanes[0].key, lane=lanes[0].lane,
                        arm=lanes[0].arm,
                        llr_sequential=lanes[0].llr_sequential,
                        observed=lanes[0].observed,
                        blind={**lanes[0].blind,
                               "ctx_state_any_adopted": True}),
               lanes[1])
    assert comb.combine(flagged, "sum").ctx_state_adopted is True
    # a lane the rule dropped is not evidence for anything it decided
    best = comb.combine(flagged, "best")
    assert best.ctx_state_adopted is bool(best.coefficients[0])


# -------------------------------------------- the sequential state vector

def test_sequential_state_matches_the_cell_the_ladder_grid_names():
    frame_syn = build_frame(R0850, key=(0, 12, 7, "C"))
    row, key = frame_syn.row, frame_syn.key
    page, ty, tx, _stream = key
    local = np.stack(np.meshgrid(np.arange(64), np.arange(64),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    cells = local + np.array([ty * 64, tx * 64], np.int64)
    n = cells.shape[0]
    bits = np.zeros((n, 3), np.uint8)
    bits[:, 1] = (local[:, 0] + local[:, 1]) % 2               # M
    bits[:, 2] = (local[:, 0] // 3) % 2                        # Y
    known = np.ones((n, 3), bool)
    known[7, 2] = False                                        # one unproven
    fp = TileFootprint(page=page, ty=ty, tx=tx, halo_cells=0,
                       page_cells_yx=cells, in_tile=np.ones(n, bool),
                       cargo=np.ones(n, bool),
                       page_shape_cells_yx=(64 * 40, 64 * 60))
    frame = KnownFrame(bits=bits, known=known, furniture=np.zeros(n, bool),
                       metadata_cell=None, regressors=known.all(axis=1),
                       labels=known[:, 0], siblings=known[:, 1] & known[:, 2],
                       n_discriminating=0, furniture_kind=None,
                       target=key, detail={})
    geometry = build_site_geometry(row)
    sequential = statecal.sequential_state(frame, fp, row, geometry, key)
    grid = L._cell_grid(row, key)
    expected = statecal.sibling_state(frame, PLANE_C).reshape(64, 64)[
        grid[:, 0], grid[:, 1]]
    assert sequential.dtype == np.int8
    assert sequential.size == row.payload_cells
    assert np.array_equal(sequential, expected)
    assert np.count_nonzero(sequential == statecal.STATE_UNKNOWN) in (0, 1)
    assert statecal.state_summary(sequential)["n_state3"] == \
        int(np.count_nonzero(expected == 3))
    with pytest.raises(ValueError):
        statecal.sequential_state(frame, fp, row, geometry,
                                  (page, ty + 1, tx, "C"))


# ------------------------------------------------------------ C3: `L7c`

def _l7c_world(hard: float = 0.08, seed: int = 909):
    frame = build_frame(R0850)
    return frame, channel_llr(frame.printed, hard, seed=seed)


def test_l7c_erases_state_cells_below_tau_within_the_cap():
    frame, llr = _l7c_world()
    llr = np.array(llr, copy=True)
    state = np.full(llr.size, np.int8(-1), np.int8)
    state[:400] = 3
    state[400:600] = 0
    llr[:400] = 0.5                            # every state-3 cell is faint
    llr[400:600] = 0.5                         # ...so is a state-0 block
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L7c",),
                           knobs={"sibling_state": state, "erase_tau": 1.0,
                                  "iters": 30},
                           exposure=Exposure(), metadata_bit=None)
    detail = results[0].detail
    assert results[0].rung == "L7c"
    assert detail["n_state_cells"] == 400
    assert detail["n_below_tau"] == 400
    assert detail["n_erased"] == 400           # state 0's block is untouched
    assert detail["erase_state"] == 3 and detail["erase_tau"] == 1.0
    assert detail["cap"] == 3976 - 3400
    assert detail["n_observed"] == 3976 - 400

    # the cap binds exactly as L7a's does
    wide = np.full(llr.size, np.int8(3), np.int8)
    capped = L.run_ladder(np.full(llr.size, 0.5), frame.row, frame.key,
                          rungs=("L7c",),
                          knobs={"sibling_state": wide, "erase_tau": 1.0,
                                 "margin": 20, "iters": 30},
                          exposure=Exposure(), metadata_bit=None)
    assert capped[0].detail["n_erased"] == 3976 - 3400 - 20
    assert capped[0].verdict != VERDICT_BELOW_FLOOR

    # a margin that eats the whole slack refuses rather than re-decoding
    # (and re-charging) L1's own channel
    exhausted = L.run_ladder(np.full(llr.size, 0.5), frame.row, frame.key,
                             rungs=("L7c",),
                             knobs={"sibling_state": wide, "erase_tau": 1.0,
                                    "margin": 4000},
                             exposure=Exposure(), metadata_bit=None)
    assert exhausted[0].verdict == VERDICT_REFUSED
    assert exhausted[0].detail["reason"] == "cap_exhausted"


def test_l7c_reproduces_the_below_floor_refusal():
    frame, llr = _l7c_world()
    llr = np.array(llr, copy=True)
    llr[:500] = 0.0                            # already unobserved
    llr[500:700] = 0.5
    state = np.full(llr.size, np.int8(-1), np.int8)
    state[500:700] = 3
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L7c",),
                           knobs={"sibling_state": state, "erase_tau": 1.0},
                           exposure=Exposure(), metadata_bit=None)
    assert results[0].verdict == VERDICT_BELOW_FLOOR
    assert results[0].detail["n_erased"] == 200
    assert results[0].detail["n_observed"] == 3976 - 700
    assert results[0].detail["bank_active_bits"] == 3400
    assert results[0].crc_consults_distinct == 0


def test_l7c_refuses_without_a_state_vector_or_without_state_cells():
    frame, llr = _l7c_world()
    exposure = Exposure()
    missing = L.run_ladder(llr, frame.row, frame.key, rungs=("L7c",),
                           knobs={}, exposure=exposure, metadata_bit=None)
    assert missing[0].verdict == VERDICT_REFUSED
    assert missing[0].detail["reason"] == "no_sibling_state"

    ragged = L.run_ladder(llr, frame.row, frame.key, rungs=("L7c",),
                          knobs={"sibling_state": np.zeros(5, np.int8)},
                          exposure=exposure, metadata_bit=None)
    assert ragged[0].detail["reason"] == "malformed_sibling_state"

    none_in_state = L.run_ladder(
        llr, frame.row, frame.key, rungs=("L7c",),
        knobs={"sibling_state": np.full(llr.size, np.int8(0), np.int8)},
        exposure=exposure, metadata_bit=None)
    assert none_in_state[0].verdict == VERDICT_REFUSED
    assert none_in_state[0].detail["reason"] == "no_state_cells"
    assert none_in_state[0].detail["n_state_cells"] == 0

    # a state-3 cell that is ALREADY erased is not erased again: doing so
    # would re-decode L1's channel and re-charge its codeword.
    already = np.array(llr, copy=True)
    already[:50] = 0.0
    zeroed = L.run_ladder(
        already, frame.row, frame.key, rungs=("L7c",),
        knobs={"sibling_state": np.where(np.arange(llr.size) < 50,
                                         np.int8(3), np.int8(-1)
                                         ).astype(np.int8),
               "erase_tau": 1.0},
        exposure=exposure, metadata_bit=None)
    assert zeroed[0].detail["reason"] == "no_state_cells"
    assert exposure.distinct == 0              # nothing was ever decoded


def test_l7c_is_direct_for_both_classifiers():
    """`oracle.is_direct` prefixes over DIRECT_RUNGS, `score` is exact."""
    from analyzer import oracle, score
    assert oracle.is_direct("L7c") is True
    assert score._is_list_rung("L7c") is False
    # and it stands on its own: no default rung list and no alias names it
    from analyzer import fixedpoint as fp
    from analyzer.types import DEFAULT_LADDER_RUNGS
    assert "L7c" not in L.DEFAULT_RUNGS
    assert "L7c" not in DEFAULT_LADDER_RUNGS
    assert "L7c" not in fp.RUNG_ALIASES.get("L7", ())
    assert "L7c" not in fp.expand_rungs(DEFAULT_LADDER_RUNGS)

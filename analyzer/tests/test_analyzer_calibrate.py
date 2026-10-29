"""W1d: the fold split, the branch-wise PAVA, the paired arm choice and
the un-permutation (DESIGN §4.7-§4.9, PLAN §1.2/§1.3).

Truth appears in exactly one place here — the sheet-I sign check, where
it is the SCORE, never an input to anything the instrument computes.
"""

from __future__ import annotations

import numpy as np
import pytest

from holo.receiver.format import keystream, tile_codec
from holo.receiver.lib import ldpc, pava
from holo.receiver.plugins import tiles as tiles_plugin

from analyzer import calibrate as cal
from analyzer.types import Evidence, KnownFrame, LaneFootprint, TileFootprint

from ._analyzer_fixtures import needs_sim, sim_run, sim_truth
from ._synthetic import R0700, row_of


# ------------------------------------------------------------- the folds

def test_split_folds_is_deterministic_and_cell_addressed():
    cells = np.stack(np.meshgrid(np.arange(40), np.arange(40),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    first = cal.split_folds(cells, 11)
    second = cal.split_folds(cells, 11)
    assert np.array_equal(first.fit, second.fit)
    assert np.array_equal(first.search, second.search)
    assert np.array_equal(first.select, second.select)
    # every cell in exactly one fold
    total = (first.fit.astype(int) + first.search.astype(int)
             + first.select.astype(int))
    assert np.all(total == 1)
    # a different seed is a different split
    other = cal.split_folds(cells, 12)
    assert not np.array_equal(first.fit, other.fit)


def test_split_folds_is_independent_of_the_footprint_it_is_asked_for():
    """A cell's fold is a function of (seed, y, x) — DESIGN §4.8.

    Two overlapping footprints must agree on every shared cell, or "the
    search fold" means something different in each tile.
    """
    big = np.stack(np.meshgrid(np.arange(0, 60), np.arange(0, 60),
                               indexing="ij"), axis=-1).reshape(-1, 2)
    small = np.stack(np.meshgrid(np.arange(20, 45), np.arange(13, 51),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    left = cal.split_folds(big, 5)
    right = cal.split_folds(small, 5)
    keys_big = big[:, 0] * 1000 + big[:, 1]
    keys_small = small[:, 0] * 1000 + small[:, 1]
    take = np.searchsorted(keys_big, keys_small)
    for name in ("fit", "search", "select"):
        assert np.array_equal(left.mask(name)[take], right.mask(name))


def test_split_folds_proportions_are_the_declared_ones():
    cells = np.stack(np.meshgrid(np.arange(200), np.arange(200),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    folds = cal.split_folds(cells, 3)
    sizes = np.asarray(folds.sizes, np.float64) / cells.shape[0]
    assert np.allclose(sizes, cal.FOLD_FRACTIONS, atol=0.01)


# --------------------------------------------------- branch-wise PAVA

def _synthetic_frame(n: int, seed: int, *, plane: int = 2,
                     cleanable_fraction: float = 0.6):
    rng = np.random.default_rng(seed)
    side = int(np.ceil(np.sqrt(n)))
    cells = np.stack(np.meshgrid(np.arange(side), np.arange(side),
                                 indexing="ij"), axis=-1).reshape(-1, 2)[:n]
    bits = rng.integers(0, 2, (n, 3), dtype=np.uint8)
    known = np.zeros((n, 3), bool)
    known[rng.random(n) < 0.5, plane] = True
    siblings = rng.random(n) < cleanable_fraction
    for other in range(3):
        if other != plane:
            known[siblings, other] = True
    fp = TileFootprint(page=0, ty=0, tx=0, halo_cells=0,
                       page_cells_yx=cells,
                       in_tile=np.ones(n, bool), cargo=np.ones(n, bool),
                       page_shape_cells_yx=(side, side))
    frame = KnownFrame(
        bits=bits, known=known, furniture=np.zeros(n, bool),
        metadata_cell=None, regressors=known.all(axis=1),
        labels=known[:, plane],
        siblings=known[:, 0] & known[:, 1] if plane == 2 else siblings,
        n_discriminating=0, furniture_kind=None,
        target=(0, 0, 0, "Y"), detail={})
    lfp = LaneFootprint(lane=("cap", 0), tile=fp,
                        observed=np.ones(n, bool),
                        owner_index=np.zeros(n, np.int32),
                        points_yx=np.zeros((n, 2)))
    return frame, lfp, cells


def test_calibrate_fits_one_map_per_branch_and_never_pools():
    """DESIGN §4.7 / blocker B12: `subtract` has two populations."""
    frame, lfp, cells = _synthetic_frame(4000, 21)
    folds = cal.split_folds(cells, 4)
    rng = np.random.default_rng(9)
    truth_bit = np.asarray(frame.bits[:, 2], np.float64)
    # the cleanable branch is quiet, the other is noisy AND offset
    score = truth_bit + rng.normal(0.0, 0.3, truth_bit.size)
    score[~frame.siblings] = (truth_bit[~frame.siblings]
                              + rng.normal(0.0, 1.2,
                                           int((~frame.siblings).sum()))
                              + 4.0)
    llr, detail = cal.calibrate(score, frame, 2, lfp, folds,
                                branches="subtract")
    assert set(detail["branches"]) == {cal.BRANCH_CLEANABLE, cal.BRANCH_OTHER}
    assert all(entry["accepted"] for entry in detail["branches"].values())
    assert np.all(np.abs(llr) <= ldpc.LLR_CLIP + 1e-9)
    # the quiet branch must read better than the noisy one
    clean = frame.siblings & frame.labels
    dirty = ~frame.siblings & frame.labels
    agree_clean = np.mean((llr[clean] > 0) == (truth_bit[clean] > 0))
    agree_dirty = np.mean((llr[dirty] > 0) == (truth_bit[dirty] > 0))
    assert agree_clean > agree_dirty
    # pooling one map over the offset mixture is measurably worse
    pooled, _ = cal.calibrate(score, frame, 2, lfp, folds, branches="pooled")
    def loss(values):
        mask = frame.labels & folds.select
        return pava._binary_logloss(values[mask], truth_bit[mask])
    assert loss(llr) < loss(pooled)


def test_calibrate_refuses_a_starved_branch_with_zero_llr():
    frame, lfp, cells = _synthetic_frame(300, 33, cleanable_fraction=0.02)
    folds = cal.split_folds(cells, 4)
    score = np.asarray(frame.bits[:, 2], np.float64)
    llr, detail = cal.calibrate(score, frame, 2, lfp, folds,
                                branches="subtract", starved_fallback=False)
    starved = detail["branches"][cal.BRANCH_CLEANABLE]
    assert not starved["accepted"]
    assert starved["reason"] in ("search_class_starved", "heldout_starved",
                                "empty_branch")
    assert np.all(llr[frame.siblings] == 0.0)


def test_fold_logloss_refuses_below_the_pava_floors():
    frame, lfp, cells = _synthetic_frame(40, 77)
    del lfp
    folds = cal.split_folds(cells, 4)
    score = np.asarray(frame.bits[:, 2], np.float64)
    assert cal.fold_logloss(score, frame, 2, folds) is None


# --------------------------------------------------------- the selection

def _evidence(arm: str, rows: np.ndarray, llr: np.ndarray,
              values: np.ndarray, discriminating: np.ndarray) -> Evidence:
    return Evidence(key=(0, 0, 0, "Y"), lane=("cap", 0), arm=arm,
                    llr_sequential=np.zeros(4), observed=np.zeros(4, bool),
                    blind={"label_rows": rows, "label_llr": llr,
                           "label_values": values,
                           "label_discriminating": discriminating,
                           "heldout_logloss_search": 0.5})


def _paired(n: int, seed: int, strength_default: float,
            strength_other: float, *, discriminating: bool = True):
    rng = np.random.default_rng(seed)
    rows = np.arange(n, dtype=np.int64)
    values = rng.integers(0, 2, n, dtype=np.uint8)
    signal = 2.0 * values.astype(np.float64) - 1.0
    default = _evidence(
        cal.DEFAULT_ARM, rows,
        strength_default * signal + rng.normal(0, 1.0, n), values,
        np.full(n, discriminating))
    other = _evidence(
        "subtract+offset", rows,
        strength_other * signal + rng.normal(0, 1.0, n), values,
        np.full(n, discriminating))
    return default, other


def test_select_arm_refuses_below_the_minority_floor():
    default, other = _paired(30, 2, 0.5, 4.0)
    winner, detail = cal.select_arm((default, other), None)
    assert winner.arm == cal.DEFAULT_ARM
    assert detail["selection_refused"] is True
    assert detail["refusal_reason"] == "below_minority_floor"


def test_select_arm_refuses_when_the_labels_do_not_discriminate():
    """DESIGN §1's corrected label arithmetic: 200 word-site labels are
    not 200 usable ones."""
    default, other = _paired(200, 3, 0.2, 4.0, discriminating=False)
    winner, detail = cal.select_arm((default, other), None)
    assert winner.arm == cal.DEFAULT_ARM
    assert detail["selection_refused"] is True


def test_select_arm_adopts_a_clearly_better_arm_above_the_floor():
    default, other = _paired(400, 4, 0.2, 4.0)
    winner, detail = cal.select_arm((default, other), None)
    assert winner.arm == "subtract+offset"
    comparison = detail["comparisons"]["subtract+offset"]
    assert comparison["adopted"] is True
    assert comparison["mean_difference"] > (
        cal.SELECT_SE_MULTIPLE * comparison["standard_error"])


def test_select_arm_keeps_the_default_on_a_tie():
    default, other = _paired(400, 5, 1.0, 1.0)
    winner, detail = cal.select_arm((default, other), None)
    assert winner.arm == cal.DEFAULT_ARM
    assert detail["comparisons"]["subtract+offset"]["adopted"] is False


# ----------------------------------------------------- the un-permuting

def test_to_sequential_is_production_s_own_scatter_and_nothing_else():
    """PLAN §1.3: un-permute ONLY; the dither stays."""
    row = row_of(R0700)
    from holo.receiver.format.identity import build_site_geometry
    geometry = build_site_geometry(row)
    page, ty, tx = 0, 9, 4
    cells = np.stack(np.meshgrid(
        np.arange(ty * 64, ty * 64 + 64),
        np.arange(tx * 64, tx * 64 + 64), indexing="ij"),
        axis=-1).reshape(-1, 2)
    fp = TileFootprint(page=page, ty=ty, tx=tx, halo_cells=0,
                       page_cells_yx=cells, in_tile=np.ones(4096, bool),
                       cargo=np.ones(4096, bool),
                       page_shape_cells_yx=(3392 // 1, 2368 // 1))
    lfp = LaneFootprint(lane=("cap", 0), tile=fp,
                        observed=np.ones(4096, bool),
                        owner_index=np.zeros(4096, np.int32),
                        points_yx=np.zeros((4096, 2)))
    rng = np.random.default_rng(1)
    values = rng.normal(0.0, 5.0, 4096)
    # the footprint is in row-major page order, so its flat local index is
    # exactly the dense index production scatters from
    dense = values.copy()
    counter = row.tile_counter(page, ty, tx)
    want, want_observed = tiles_plugin._sequential_payload(
        row, geometry, counter, dense, np.ones(4096, bool))
    got, got_observed = cal.to_sequential(values, lfp, row, geometry,
                                          (page, ty, tx, "C"))
    assert np.array_equal(got, want)
    assert np.array_equal(got_observed, want_observed)
    assert got.size == row.payload_cells


def test_to_sequential_marks_unobserved_cells_and_zeroes_them():
    row = row_of(R0700)
    from holo.receiver.format.identity import build_site_geometry
    geometry = build_site_geometry(row)
    page, ty, tx = 0, 3, 3
    cells = np.stack(np.meshgrid(
        np.arange(ty * 64, ty * 64 + 64),
        np.arange(tx * 64, tx * 64 + 64), indexing="ij"),
        axis=-1).reshape(-1, 2)
    observed = np.ones(4096, bool)
    observed[:1000] = False
    fp = TileFootprint(page=page, ty=ty, tx=tx, halo_cells=0,
                       page_cells_yx=cells, in_tile=np.ones(4096, bool),
                       cargo=np.ones(4096, bool),
                       page_shape_cells_yx=(3392, 2368))
    lfp = LaneFootprint(lane=("cap", 0), tile=fp, observed=observed,
                        owner_index=np.zeros(4096, np.int32),
                        points_yx=np.zeros((4096, 2)))
    values = np.full(4096, 7.0)
    llr, seen = cal.to_sequential(values, lfp, row, geometry,
                                  (page, ty, tx, "M"))
    assert int(np.count_nonzero(~seen)) > 0
    assert np.all(llr[~seen] == 0.0)
    assert np.all(llr[seen] == 7.0)


# --------------------------------------------------------- sheet I

#: The configuration DESIGN §4.6's own production arm composes (a blind
#: offset search, then production's region context); the pinned default
#: is reported beside it because the GAP is the measurement.
SIGN_CONFIGURATIONS: tuple[tuple[str, str], ...] = (
    ("subtract+committed", "none"),
    ("subtract+offset", "production"),
)
SIGN_GATE_CONFIGURATION = ("subtract+offset", "production")


@needs_sim
def test_the_llr_sign_agrees_with_the_emitted_bits():
    """Q1-shaped: one certified tile per stream, read blind, scored, on
    the receiver's displaced colour sim decoded into a run dir (TIER S).

    The target's own certificate is hidden from the frame by
    `frame.known_frame`, so the LLR is produced without ever seeing the
    answer; the emitted bits are re-derived here, in the TEST, as
    `encode_frame(gt_user) ^ dither` — the as-printed sequential domain
    `to_sequential` returns.  ONE lane, so the number is a single
    capture's cell-level agreement, not the union's.
    """
    from analyzer import arms, sample
    run = sim_run()
    truth = sim_truth()
    page = run.live_pages[0]
    table: dict[tuple[str, str], dict[str, tuple[float, int]]] = {}
    for arm, ctx_mode in SIGN_CONFIGURATIONS:
        rates: dict[str, tuple[float, int]] = {}
        for stream in ("C", "M", "Y"):
            key = _pick_certified(run, page, stream, 1)[0]
            lane = sample.lanes_for_tile(run, *key[:3])[0]
            evidence = arms.evidence_for(
                run, run.certificates, key, lane, arm,
                knobs={"mix_scope_ladder": ("footprint",),
                       "ctx_mode": ctx_mode, "seed": 5})
            assert evidence.blind.get("refusal") is None, evidence.blind
            printed = _printed_bits(run.row, key, truth.user_bits[key])
            seen = np.asarray(evidence.observed, bool)
            rates[stream] = (float(np.mean(
                (np.asarray(evidence.llr_sequential)[seen] > 0)
                == (printed[seen] > 0))), int(seen.sum()))
        table[(arm, ctx_mode)] = rates
    print("\nsign agreement with the emitted bits, one lane, one certified "
          "tile per stream:")
    for (arm, ctx_mode), rates in table.items():
        print(f"  {arm:20s} ctx={ctx_mode:11s} "
              + "  ".join(f"{stream} {value[0]:.4f} ({value[1]} cells)"
                          for stream, value in rates.items()))
    gate = table[SIGN_GATE_CONFIGURATION]
    for stream in ("C", "M"):
        assert gate[stream][0] >= 0.90, gate


def _printed_bits(row, key, user_bits) -> np.ndarray:
    from holo.receiver.plugins.tiles import stream_fact
    fact = stream_fact(row, key[3])
    counter = row.tile_counter(*key[:3])
    return (tile_codec.encode_frame(np.asarray(user_bits, np.uint8),
                                    fact.rung_children)
            ^ keystream.cmy8_dither_bits(row.seed, key[3], counter,
                                         row.payload_cells))


def _pick_certified(run, page: int, stream: str, count: int):
    keys = sorted(key for key in run.certificates
                  if key[0] == page and key[3] == stream
                  and 1 <= key[1] <= run.tiles_yx[0] - 2
                  and 1 <= key[2] <= run.tiles_yx[1] - 2)
    if not keys:
        pytest.skip(f"no interior certified {stream} tile")
    step = max(1, len(keys) // count)
    return [keys[index * step] for index in range(count)]

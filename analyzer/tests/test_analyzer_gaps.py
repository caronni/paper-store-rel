"""Guards for the C-parity findings of `analyzer/GAPS-2026-09-03.md`.

The measurement is in `analyzer/sweeps/c_parity_gap.py`; these are the two
pins it earned:

* the two-population split of DESIGN §4.7 can starve the branch that holds
  the ENTIRE target tile, which erases the tile rather than mispricing it;
* `branches` is reachable as a knob, so a measurement can ask the same arm
  for the pooled map production fits, and the default is still the mode.
"""

from __future__ import annotations

import numpy as np

from analyzer import calibrate as cal
from analyzer import fixedpoint as fp
from analyzer.types import (AnalyzerConfig, KnownFrame, LaneFootprint,
                            TileFootprint)


def _halo_clean_frame(tile_cells: int = 300, halo_cells: int = 900,
                      *, plane: int = 0, seed: int = 5):
    """A footprint whose halo is fully cleanable and whose tile is not.

    That is sheet H's (0, 34, 34, C): every neighbour certified in all
    three planes, the target's own Y sibling missing.  The tile's cells
    are then the WHOLE `other` branch and carry no proven label.
    """
    rng = np.random.default_rng(seed)
    n = tile_cells + halo_cells
    side = int(np.ceil(np.sqrt(n)))
    cells = np.stack(np.meshgrid(np.arange(side), np.arange(side),
                                 indexing="ij"), axis=-1).reshape(-1, 2)[:n]
    in_tile = np.zeros(n, bool)
    in_tile[:tile_cells] = True
    bits = rng.integers(0, 2, (n, 3), dtype=np.uint8)
    known = np.zeros((n, 3), bool)
    known[~in_tile, :] = True             # the halo is proven in all planes
    siblings = ~in_tile                   # so only the halo is cleanable
    frame = KnownFrame(
        bits=bits, known=known, furniture=np.zeros(n, bool),
        metadata_cell=None, regressors=known.all(axis=1),
        labels=known[:, plane], siblings=siblings, n_discriminating=0,
        furniture_kind=None, target=(0, 34, 34, "C"), detail={})
    footprint = TileFootprint(page=0, ty=34, tx=34, halo_cells=16,
                              page_cells_yx=cells, in_tile=in_tile,
                              cargo=in_tile, page_shape_cells_yx=(side, side))
    lfp = LaneFootprint(lane=("cap", 0), tile=footprint,
                        observed=np.ones(n, bool),
                        owner_index=np.zeros(n, np.int32),
                        points_yx=np.zeros((n, 2)))
    return frame, lfp, cells, in_tile


def test_the_branch_split_can_erase_the_whole_target_tile():
    """The DEFECT, with the amendment of DESIGN §4.7 switched off.

    `starved_fallback` is the amendment (2026-09-03) and is now the
    default, so this pin — which describes what the unamended split does —
    asks for the unamended behaviour explicitly.  That the fallback
    repairs it is
    `test_analyzer_gaps_fix.py::test_the_default_prices_the_tile_the_split_used_to_erase`.
    """
    frame, lfp, cells, in_tile = _halo_clean_frame()
    folds = cal.split_folds(cells, 4)
    rng = np.random.default_rng(11)
    score = np.asarray(frame.bits[:, 0], np.float64) + rng.normal(
        0.0, 0.3, cells.shape[0])
    llr, detail = cal.calibrate(score, frame, 0, lfp, folds,
                                branches="subtract", ctx_mode="none",
                                starved_fallback=False)
    other = detail["branches"][cal.BRANCH_OTHER]
    assert other["n_cells"] == int(np.count_nonzero(in_tile))
    assert other["n_fit_0"] == 0 and other["n_fit_1"] == 0
    assert not other["accepted"]
    assert other["reason"] == "search_class_starved"
    # every cargo cell of the target tile is erased, though the score is good
    assert np.all(llr[in_tile] == 0.0)
    assert np.any(llr[~in_tile] != 0.0)


def test_the_pooled_map_prices_the_tile_the_split_erased():
    frame, lfp, cells, in_tile = _halo_clean_frame()
    folds = cal.split_folds(cells, 4)
    rng = np.random.default_rng(11)
    score = np.asarray(frame.bits[:, 0], np.float64) + rng.normal(
        0.0, 0.3, cells.shape[0])
    pooled, detail = cal.calibrate(score, frame, 0, lfp, folds,
                                   branches="pooled", ctx_mode="none")
    assert set(detail["branches"]) == {cal.BRANCH_ALL}
    assert np.count_nonzero(pooled[in_tile]) == int(np.count_nonzero(in_tile))
    agree = np.mean((pooled[in_tile] > 0)
                    == (frame.bits[in_tile, 0] > 0))
    assert agree > 0.9


def test_the_branches_knob_reaches_the_arm_and_defaults_to_pooled():
    """`config.knobs` is merged last, so a measurement can set `branches`.

    The default moved on 2026-09-03 from "the unmix mode" (the §4.7 split)
    to `cal.DEFAULT_BRANCHES` = pooled, on the gate in
    `analyzer/GAPS-2026-09-03.md` §8; the KNOB is unchanged and still
    reaches the arm, which is what this pins.
    """
    class _Inputs:
        plane_fields: dict = {}

    class _Lane:
        capture_id = "cap"
        level_index = 0

    key = (0, 34, 34, "C")
    default = fp._knobs_for(_Inputs(), AnalyzerConfig(), key, _Lane(),
                            None, None)
    assert "branches" not in default
    asked = fp._knobs_for(_Inputs(), AnalyzerConfig(knobs={"branches":
                                                           "pooled"}),
                          key, _Lane(), None, None)
    assert asked["branches"] == "pooled"
    # the arm's own default: absent or empty knob means DEFAULT_BRANCHES
    for value in (None, "", "subtract"):
        assert str(value or cal.DEFAULT_BRANCHES) == (
            "subtract" if value == "subtract" else cal.DEFAULT_BRANCHES)

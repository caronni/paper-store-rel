from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
import pytest

from holo.receiver import data
from holo.receiver.format import identity
from holo.receiver.format.identity import resolve_format_ref
from holo.receiver.lib import geometry
from holo.receiver.plugins import cold, place, place_pass, pose, words
from holo.receiver.tests import _h3_support

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_cold_hypothesis_count_is_the_declared_domain`,
# `test_pass_budget_scales_with_tried_and_offered_hypotheses`,
# `test_placement_gate_row_is_frozen`,
# `test_single_word_probability_matches_its_own_union_bound`,
# `test_stage_a_hypothesis_count_is_a_pure_function_of_the_shape`,
# `test_stage_a_refuses_a_fragment_below_the_visible_site_floor`,
# `test_stage_price_is_monotone_in_stage_lane_depth_and_child_premium`,
# `test_window_plan_tiles_the_region_on_the_declared_lattice`.

# frozen 2026-08-29 from tests/holo/test_placement_policy_golden.py:33 —
# the RECEIVE-DESIGN §5.3 domain table, hand-copied
DOMAIN_TABLE = (
    (49, 30), (392, 30), (16_926_660, 41), (35_312_324, 42),
    (87_551_308, 45), (4_943_725_360, 54), (5_281_117_920, 55),
    (15_168_568_640, 57))

P_MAX = 0.08

K_FOSSIL = "L:c3-r0550@2240x1536"
TINY_ROW = "c3-k-r0550@2x2"

COLD_FRAGMENT_CELLS = 96
COLD_ORIGIN_YX = (18, 27)


def test_placement_gate_row_is_frozen():
    _h3_support.assert_measured("GATE_SEARCH_TRUE", place.GATE_SEARCH_TRUE,
                               0.20)
    _h3_support.assert_measured("GATE_RIVAL_DECOY", place.GATE_RIVAL_DECOY,
                               0.20)
    _h3_support.assert_measured("GATE_MINIMUM_GAP", place.GATE_MINIMUM_GAP,
                               0.08)
    _h3_support.assert_measured("GATE_VALIDATION_TRUE",
                               place.GATE_VALIDATION_TRUE, 0.24)
    _h3_support.assert_measured("E022_SUPPORT_FLOOR_SITES",
                               place.E022_SUPPORT_FLOOR_SITES, 30)
    _h3_support.assert_measured("BER_ENVELOPE", place.BER_ENVELOPE, 0.08)
    _h3_support.assert_measured("SUPPORT_MARGIN_SITES",
                               place.SUPPORT_MARGIN_SITES, 0)
    _h3_support.assert_measured("WORD_FALSE_ACCEPT", words.WORD_FALSE_ACCEPT,
                               1e-3)


def test_single_word_probability_matches_its_own_union_bound():
    from holo.receiver.lib import bch

    recomputed = math.ldexp(
        float(sum(math.comb(100, errors) for errors in range(bch.T + 1))),
        18 - 100)
    _h3_support.assert_measured("SINGLE_WORD_PROBABILITY",
                               words.SINGLE_WORD_PROBABILITY,
                               1.7209511801042833e-09)
    assert recomputed == words.SINGLE_WORD_PROBABILITY


@pytest.mark.parametrize("hypotheses,floor", DOMAIN_TABLE)
def test_min_support_reproduces_the_design_domain_table(hypotheses, floor):
    entropy = (-P_MAX * math.log2(P_MAX)
               - (1.0 - P_MAX) * math.log2(1.0 - P_MAX))
    assert place.min_support_for(hypotheses) == floor
    assert place.min_support_for(hypotheses) == max(
        place.E022_SUPPORT_FLOOR_SITES,
        math.ceil(math.log2(hypotheses) / (1.0 - entropy)))


@pytest.mark.parametrize(
    "hypotheses,expected",
    [(1, 0), (2, 2), (1024, 17), (35_312_324, 42)])
def test_identifiability_support_floor_boundary_values(hypotheses, expected):
    assert place.identifiability_support_floor(hypotheses, P_MAX) == expected


def test_a_noiseless_channel_needs_only_log2_hypotheses_sites():
    assert place.identifiability_support_floor(1024, 0.0) == 10
    assert place.identifiability_support_floor(35_312_324, 0.0) == 26


def test_pass_budget_scales_with_tried_and_offered_hypotheses():
    _h3_support.assert_measured("LOCAL_HYPOTHESES", place.LOCAL_HYPOTHESES, 49)
    assert place.pass_budget_hypotheses(0, 0) == 49
    assert place.pass_budget_hypotheses(0, 8) == 49 * 8
    assert place.pass_budget_hypotheses(3, 5) == 49 * 8


def test_stage_price_is_monotone_in_stage_lane_depth_and_child_premium():
    _h3_support.assert_measured(
        "stage_price at depth 0, lane 0",
        {stage: place.stage_price(stage, 0, 0)
         for stage in place.STAGE_COST},
        # `subdivide` joined 2026-09-21 at the RING's price: the one
        # literal the ladder gained when the quartering became a rung,
        # equal to an existing one by construction.
        {"ring": 40, "subdivide": 40, "word_centre": 60, "word_rest": 80,
         "wide": 120, "cold_live": 250, "cold_rest": 260})
    for stage in place.STAGE_COST:
        assert place.stage_price(stage, 1, 0) > place.stage_price(
            stage, 0, 0)
        assert place.stage_price(stage, 0, 1) == (
            place.stage_price(stage, 0, 0) + place.CHILD_PREMIUM)
    assert place.stage_price("cold_live", 1, 0) - place.stage_price(
        "cold_live", 0, 0) == place.COLD_COST_PER_RUNG
    assert place.stage_price("ring", 1, 0) - place.stage_price(
        "ring", 0, 0) == place.LANE_COST_PER_RUNG


def _stage(offered=False, centre=False, rest=False, wide=False,
           cold_armed=False, live_ready=False, live_spent=False,
           rest_ready=False, rest_spent=False, armed=False,
           ready=False, support=False) -> str | None:
    """`place.stage_of` with the ladder's state named, not counted."""
    return place.stage_of(offered, centre, rest, wide, cold_armed,
                          live_ready, live_spent, rest_ready, rest_spent,
                          subdivide_armed=armed, subdivide_ready=ready,
                          support_refused=support)


def test_stage_of_walks_the_ladder_in_order():
    assert _stage(offered=True) == place.STAGE_RING
    assert _stage() == place.STAGE_WORD_CENTRE
    assert _stage(centre=True) == place.STAGE_WORD_REST
    assert _stage(centre=True, rest=True) == place.STAGE_WIDE
    assert _stage(centre=True, rest=True, wide=True, cold_armed=True,
                  live_ready=True) == place.STAGE_COLD_LIVE
    assert _stage(centre=True, rest=True, wide=True, cold_armed=True,
                  live_ready=True, live_spent=True,
                  rest_ready=True) == place.STAGE_COLD_REST
    assert _stage(centre=True, rest=True, wide=True, cold_armed=True,
                  live_ready=True, live_spent=True, rest_ready=True,
                  rest_spent=True) is None
    assert _stage(centre=True, rest=True, wide=True, live_ready=True,
                  rest_ready=True) is None


def test_the_quartering_is_a_rung_armed_early_or_taken_last():
    """The two halves of subdivision, 2026-09-21.

    ARMED, by a refusal of the window's own fit or of an address it had
    already accepted: the rung comes before the rest of the ladder, as
    v1's fold did it.  LAZY: correlation is exhausted first and the
    quartering is the last thing the window does.  RING outranks both —
    a seed that arrived while the window waited is tried before it is
    cut up, which is why this decision is a rung evaluated at the pop
    and not a verdict the pass carries.  A window that cannot quarter
    (depth cap, or under the minimum window) is never offered it.
    """
    assert _stage(armed=True, ready=True) == place.STAGE_SUBDIVIDE
    assert _stage(offered=True, armed=True,
                  ready=True) == place.STAGE_RING
    assert _stage(armed=True, ready=False) == place.STAGE_WORD_CENTRE
    assert _stage(centre=True, rest=True, wide=True, cold_armed=True,
                  live_ready=True, live_spent=True, rest_ready=True,
                  rest_spent=True, ready=True) == place.STAGE_SUBDIVIDE
    # too little paper (`insufficient_support`) spends every rung but
    # an ARMED quartering -- ahead of an untried consult too, and never
    # the lazy one (review 2026-10-17, D1)
    assert _stage(support=True, offered=True, armed=True,
                  ready=True) == place.STAGE_SUBDIVIDE
    assert _stage(support=True, offered=True, ready=True) is None
    assert _stage(support=True, armed=True, ready=False) is None
    frame = _frame((500, 500))
    parent = place.window_plan(frame, lane_depth=0)[0]
    assert place.subdividable(parent) is True
    assert all(place.subdividable(child) is False
               for child in place.child_windows(frame, parent, 0)), (
        "depth 1 is the cap: a child has no children, so its spent "
        "ladder is spent")


def test_cold_flavour_pages_partition_the_page_domain():
    domain = (0, 1, 2, 3, 4)
    live = frozenset({1, 3})
    assert place.cold_flavour_pages(
        domain, place.STAGE_COLD_LIVE, live) == (1, 3)
    assert place.cold_flavour_pages(
        domain, place.STAGE_COLD_REST, live) == (0, 2, 4)
    assert place.cold_tried_id(7, place.STAGE_COLD_LIVE) == (
        "cold-page/cold_live/7")
    assert place.cold_tried_id(7, place.STAGE_COLD_REST) == (
        "cold-page/cold_rest/7")
    assert (place.cold_tried_id(7, place.STAGE_COLD_LIVE)
            != place.cold_tried_id(7, place.STAGE_COLD_REST))


def test_rest_is_empty_when_live_covers_possible():
    domain = (0,)
    live = frozenset({0})
    assert place.cold_flavour_pages(
        domain, place.STAGE_COLD_REST, live) == ()
    assert place.cold_flavour_pages(
        domain, place.STAGE_COLD_LIVE, live) == (0,)


def _region(shape_cells: tuple[int, int], step_px: int,
            pitch_px: float) -> data.Region:
    cells = np.ones(
        (int(shape_cells[0] * pitch_px) // step_px + 1,
         int(shape_cells[1] * pitch_px) // step_px + 1), bool)
    cells.setflags(write=False)
    return data.Region(
        capture_id="cap", region_index=0, origin_yx=(64, 96),
        step_px=step_px, cells=cells,
        extent_px=(int(shape_cells[0] * pitch_px),
                   int(shape_cells[1] * pitch_px)),
        area_mm2=100.0, median_tensor_score=1.0)


def _level(index: int, scale: int) -> data.Level:
    return data.Level(index=index, ppc=Fraction(2), scale=Fraction(scale),
                      shape_px=(1000, 1000), label=f"l{index:02d}")


def test_region_frame_derives_the_cell_grid_from_the_printed_pitch():
    pitch_in = Fraction(1, 200)
    dpi = 1200.0
    pitch_px = float(pitch_in) * dpi
    region = _region((300, 260), 16, pitch_px)
    frame = place.region_frame(region, _level(1, 2), pitch_in, dpi, 240.0)
    assert frame is not None
    assert frame.pitch_native_px == pitch_px
    assert frame.pitch_level_px == pitch_px / 2.0
    assert frame.shape_cells == (300, 260)
    assert frame.origin_native_yx == (64, 96)
    assert frame.origin_level_yx == (32, 48)
    assert frame.scale == 2
    assert frame.support_cells.shape == (300, 260)
    assert frame.support_cells.all()
    assert frame.backing == 240.0


def test_region_frame_refuses_a_region_with_no_supported_cell():
    pitch_in = Fraction(1, 200)
    region = _region((300, 260), 16, float(pitch_in) * 1200.0)
    empty = data.Region(
        capture_id=region.capture_id, region_index=0,
        origin_yx=region.origin_yx, step_px=region.step_px,
        cells=np.zeros(region.cells.shape, bool),
        extent_px=region.extent_px, area_mm2=0.0,
        median_tensor_score=0.0)
    assert place.region_frame(empty, _level(1, 2), pitch_in, 1200.0,
                              240.0) is None


def _frame(shape_cells: tuple[int, int]) -> place.RegionFrame:
    pitch_in = Fraction(1, 200)
    dpi = 1200.0
    region = _region(shape_cells, 16, float(pitch_in) * dpi)
    frame = place.region_frame(region, _level(1, 2), pitch_in, dpi, 240.0)
    assert frame is not None
    return frame


def test_window_plan_tiles_the_region_on_the_declared_lattice():
    frame = _frame((500, 500))
    windows = place.window_plan(frame, lane_depth=1, first_ordinal=10)
    starts = geometry.window_starts(500)
    _h3_support.assert_measured("window starts on a 500-cell axis", starts,
                               (0, 160, 300))
    assert len(windows) == len(starts) ** 2
    assert tuple(w.ordinal for w in windows) == tuple(
        range(10, 10 + len(windows)))
    extents = {w.extent_cells for w in windows}
    assert (0, 0, 200, 200) in extents
    assert (300, 300, 500, 500) in extents
    for window in windows:
        assert window.depth == 0
        assert window.lane_depth == 1
        assert window.supported_cells == 200 * 200
        assert window.window_id == ("cap", 1, 0, window.extent_cells)


def test_window_plan_skips_windows_with_no_support():
    frame = _frame((500, 500))
    support = np.array(frame.support_cells, copy=True)
    support[300:, 300:] = False
    blinded = type(frame)(**{**frame.__dict__, "support_cells": support})
    windows = place.window_plan(blinded, lane_depth=0)
    assert (300, 300, 500, 500) not in {w.extent_cells for w in windows}
    assert len(windows) == 8


def test_ring_neighbour_extents_are_the_eight_lattice_neighbours():
    frame = _frame((500, 500))
    middle = place.ring_neighbour_extents(
        frame.shape_cells, (160, 160, 360, 360))
    assert len(middle) == 8
    assert (160, 160, 360, 360) not in middle
    corner = place.ring_neighbour_extents(
        frame.shape_cells, (0, 0, 200, 200))
    assert len(corner) == 3
    assert place.ring_neighbour_extents(
        frame.shape_cells, (7, 0, 207, 200)) == ()


def test_child_windows_stay_inside_the_frame_and_take_a_new_depth():
    frame = _frame((500, 500))
    parent = place.window_plan(frame, lane_depth=0)[0]
    children = place.child_windows(frame, parent, first_ordinal=100)
    assert len(children) == 4
    for index, child in enumerate(children):
        assert child.depth == 1
        assert child.ordinal == 100 + index
        cy0, cx0, cy1, cx1 = child.extent_cells
        assert 0 <= cy0 < cy1 <= 500 and 0 <= cx0 < cx1 <= 500
        assert (cy1 - cy0, cx1 - cx0) == (100, 100)
    assert place.child_windows(
        frame, children[0], first_ordinal=0) == ()


def _anchor(pose_id: str, extent: tuple[int, int, int, int],
            page: int) -> place.AnchorPose:
    return place.AnchorPose(pose_id, extent, page,
                            (6.0, 0.0, 10.0, 0.0, 6.0, 20.0))


def test_consult_seeds_ranks_by_lattice_distance_then_candidate_id():
    anchors = (
        _anchor("far", (0, 0, 200, 200), 0),
        _anchor("near", (160, 160, 360, 360), 0),
        _anchor("off-domain", (160, 160, 360, 360), 9),
    )
    seeds = place.consult_seeds((160, 320, 360, 520), anchors, (0,),
                                wide=False)
    assert tuple(seed.candidate_id for seed in seeds) == ("near", "far")
    assert seeds[0].distance == pytest.approx(1.0)
    assert seeds[1].distance == pytest.approx(math.hypot(1.0, 2.0))
    assert all(seed.page == 0 for seed in seeds)


def test_consult_seeds_keeps_more_anchors_on_the_wide_tier():
    anchors = tuple(
        _anchor(f"a{index:02d}", (160 * index, 0, 160 * index + 200, 200), 0)
        for index in range(12))
    assert len(place.consult_seeds((0, 0, 200, 200), anchors, (0,),
                                   wide=False)) == place.CONSULT_KEEP
    assert len(place.consult_seeds((0, 0, 200, 200), anchors, (0,),
                                   wide=True)) == place.WIDE_ANCHORS


def test_seed_rank_prefers_more_support_then_the_window_id():
    small = ("cap", 0, 0, (0, 0, 200, 200))
    large = ("cap", 0, 0, (160, 0, 360, 200))
    assert place.seed_rank(500, small) < place.seed_rank(400, large)
    assert place.seed_supersedes(500, large, 400, small) is True
    assert place.seed_supersedes(400, large, 500, small) is False
    assert place.seed_supersedes(400, small, 400, large) is True
    assert place.seed_supersedes(400, large, 400, small) is False


@pytest.mark.parametrize(
    "done_value,support_value,covers",
    [(True, True, True), (False, True, False), (False, False, False)])
def test_done_covers_is_evaluated_only_over_supported_cells(
        done_value, support_value, covers):
    done = np.full((8, 8), done_value)
    support = np.full((8, 8), support_value)
    assert place.done_covers(done, support, (0, 0, 8, 8)) is covers


def test_partially_supported_windows_close_when_their_support_is_done():
    done = np.zeros((8, 8), bool)
    support = np.zeros((8, 8), bool)
    support[2:4, 2:4] = True
    done[2:4, 2:4] = True
    assert place.done_covers(done, support, (0, 0, 8, 8)) is True
    done[3, 3] = False
    assert place.done_covers(done, support, (0, 0, 8, 8)) is False


@pytest.fixture(scope="module")
def k_row() -> object:
    return resolve_format_ref(K_FOSSIL)


@pytest.fixture(scope="module")
def k_reference(k_row) -> words.ReferenceField:
    return words.ReferenceField(k_row)


def test_reference_page_puts_word_values_at_every_word_site(k_row,
                                                            k_reference):
    from holo.receiver.format import pilots

    page = k_reference.page(0)
    assert page.values.shape == k_row.cells_yx
    assert page.sites.shape == k_row.cells_yx
    assert int(page.sites.sum()) == k_row.tiles_per_page * k_row.n_sites
    geometry_word = pilots.word_site_cells_yx(k_row.sites_seed)
    counter = k_row.tile_counter(0, 2, 3)
    expected = pilots.word_values(k_row.seed, counter,
                                  k_row.streams[0].plane)[0]
    read = page.values[2 * 64 + geometry_word[:, 0],
                       3 * 64 + geometry_word[:, 1]]
    assert np.array_equal(read, expected)
    assert k_reference.page(0) is page


#: Every identity the fossil catalogue freezes, the small registered rows
#: of each family, and four rows off the p120 lineage — the furniture
#: density axis `p` (n_dust = p - 100 for colour, n_filler = p - 100 for
#: K), which is lawful for cmy8 over p in [101, 2206] and which
#: `capacity` has always priced.
SITE_INVARIANT_REFS = tuple(
    ["L:" + fossil for fossil in sorted(identity._FOSSILS)]
    + ["c3-k-r0550@2x2", "c2-cmy8-r0550@2x2", "c3-cmy7@2x2",
       "c2-cmy8-r0550-p101@2x2", "c2-cmy8-r0550-p172@2x2",
       "c2-cmy8-r0550-p300@2x2", "c2-k-r0700-p300@2x2"])


@pytest.mark.parametrize("ref", SITE_INVARIANT_REFS)
def test_the_reference_field_stands_on_the_row_s_own_site_geometry(ref: str):
    """The addressing reference reads the SAME sites the row declares.

    `store.__init__` builds `identity.build_site_geometry(row)` at
    store.py:32 and, nine lines later at store.py:41, hands the row to
    `words.ReferenceField`, which re-derives the same geometry for
    itself — and nothing compared the two.  Until 2026-09-16 the second
    derivation was not the first: `words._site_cells` hardcoded 20 dust
    whatever the row said, so the reference field CONSTRUCTED over a
    mask carrying 12,000 of a p300 page's 30,000 sites and complained
    only on first page touch, with `ValueError: shape mismatch: value
    array of shape (100,200) could not be broadcast to indexing result
    of shape (100,20)`.
    """
    row = resolve_format_ref(ref)
    geometry = identity.build_site_geometry(row)
    cells = np.concatenate(
        [geometry.word_cells_yx, geometry.extra_cells_yx], axis=0)
    assert cells.shape == (row.n_sites, 2)

    tiles_y, tiles_x = row.tiles_yx
    tile = np.arange(tiles_y * tiles_x, dtype=np.int64)
    declared = np.zeros(row.cells_yx, bool)
    declared[(tile // tiles_x)[:, None] * 64 + cells[None, :, 0],
             (tile % tiles_x)[:, None] * 64 + cells[None, :, 1]] = True
    assert np.array_equal(words._site_mask(row), declared)
    assert int(words.reference_page(row, 0).sites.sum()) == (
        row.n_sites * row.tiles_per_page)


def test_stage_a_recovers_every_whole_word_in_a_clean_fragment(k_row,
                                                               k_reference):
    page = k_reference.page(0)
    origin = (128, 192)
    shape = (128, 128)
    bits = page.values[origin[0]:origin[0] + shape[0],
                       origin[1]:origin[1] + shape[1]].copy()
    result = words.stage_a(bits, np.ones(shape, bool), k_row)
    assert result.reason == "candidates"
    assert result.hypotheses == words.stage_a_hypotheses(shape)
    assert len(result.candidates) == 4
    assert tuple(c.counter for c in result.candidates) == (51, 52, 75, 76)
    assert {c.page_origin_yx for c in result.candidates} == {origin}
    assert {c.rot_k for c in result.candidates} == {0}
    assert {c.errors for c in result.candidates} == {0}
    assert tuple(c.tile_yx for c in result.candidates) == (
        (2, 3), (2, 4), (3, 3), (3, 4))


def test_stage_a_refuses_a_fragment_whose_budget_exceeds_the_word_bar(k_row):
    shape = (900, 900)
    hypotheses = words.stage_a_hypotheses(shape)
    assert hypotheses * words.SINGLE_WORD_PROBABILITY > (
        words.WORD_FALSE_ACCEPT)
    result = words.stage_a(np.zeros(shape, np.uint8),
                           np.zeros(shape, bool), k_row)
    assert result.reason == "attempt_budget_exceeded"
    assert result.candidates == ()
    assert result.hypotheses == hypotheses


def test_stage_a_refuses_a_fragment_below_the_visible_site_floor(
        k_row, k_reference):
    page = k_reference.page(0)
    origin = (128, 192)
    shape = (128, 128)
    bits = page.values[origin[0]:origin[0] + shape[0],
                       origin[1]:origin[1] + shape[1]].copy()
    mask = np.zeros(shape, bool)
    mask[:20, :20] = True
    _h3_support.assert_measured("STAGE_A_MIN_VISIBLE_SITES",
                               words.STAGE_A_MIN_VISIBLE_SITES, 90)
    assert words.stage_a(bits, mask, k_row).candidates == ()


def test_stage_a_stage_selection_splits_the_slot_grid(k_row, k_reference):
    _h3_support.skip_unless_slow_lane("the three-way stage_a slot-grid split")
    page = k_reference.page(0)
    shape = (192, 192)
    bits = page.values[128:128 + shape[0], 192:192 + shape[1]].copy()
    mask = np.ones(shape, bool)
    everything = words.stage_a(bits, mask, k_row, words.STAGE_ALL)
    centre = words.stage_a(bits, mask, k_row, words.STAGE_CENTRE)
    rest = words.stage_a(bits, mask, k_row, words.STAGE_REST)
    assert len(centre.candidates) + len(rest.candidates) == len(
        everything.candidates)
    assert len(centre.candidates) == 1
    assert not set(c.counter for c in centre.candidates) & set(
        c.counter for c in rest.candidates)


def test_stage_a_hypothesis_count_is_a_pure_function_of_the_shape():
    _h3_support.assert_measured("stage_a_hypotheses (200,200)",
                               words.stage_a_hypotheses((200, 200)), 147456)
    _h3_support.assert_measured("stage_a_hypotheses (128,128)",
                               words.stage_a_hypotheses((128, 128)), 65536)
    _h3_support.assert_measured("stage_a_hypotheses (100,120)",
                               words.stage_a_hypotheses((100, 120)), 8436)
    assert words.stage_a_hypotheses((63, 400)) == 0
    assert words.stage_a_hypotheses((100, 120)) == words.stage_a_hypotheses(
        (120, 100))


def _candidate(page: int, origin: tuple[int, int], rot_k: int,
               counter: int) -> words.WordCandidate:
    return words.WordCandidate((0, 0), rot_k, counter, page, (0, 0), 0,
                               origin)


def test_word_rival_rows_drops_the_winner_and_its_local_neighbourhood():
    winner = _candidate(0, (100, 100), 0, 1)
    inside = _candidate(0, (102, 99), 0, 2)
    outside = _candidate(0, (120, 100), 0, 3)
    other_rot = _candidate(0, (100, 100), 1, 4)
    rows = words.word_rival_rows(
        winner, (winner, inside, outside, other_rot), (0, 1), radius=3)
    assert (0, (102, 99), 0) not in rows
    assert (0, (120, 100), 0) in rows
    assert (0, (100, 100), 1) in rows
    assert (1, (100, 100), 0) in rows
    assert (0, (100, 100), 0) not in rows
    assert len(rows) == len(set(rows))


def test_word_rival_rows_always_offers_every_page_as_a_decoy():
    winner = _candidate(0, (100, 100), 0, 1)
    rows = words.word_rival_rows(winner, (winner,), (0, 1, 2), radius=3)
    assert rows == ((1, (100, 100), 0), (2, (100, 100), 0))


def test_word_admission_reads_the_possible_domain():
    import inspect
    source = inspect.getsource(place_pass.run_window_pass)
    assert "result.candidates, job.page_domain, floor)" in source
    assert "job.live_pages or job.page_domain" not in source


def test_the_committed_pose_carries_window_local_cells_at_int16():
    audited = np.zeros((7, 9), bool)
    audited[0, 0] = audited[3, 4] = audited[6, 8] = True
    cells = place_pass.local_cells_of(audited)
    assert cells.dtype == np.int16
    assert np.array_equal(cells, np.asarray([[0, 0], [3, 4], [6, 8]]))


def test_the_minted_cells_refuse_a_window_int16_cannot_address():
    """The width is a storage choice with 163x of headroom over the
    largest window this record has placed; a coordinate past it is a
    broken frame, and wrapping one would move a pose silently."""
    audited = np.zeros((np.iinfo(np.int16).max + 2, 1), bool)
    audited[-1, 0] = True
    with pytest.raises(ValueError, match="exceeds int16"):
        place_pass.local_cells_of(audited)


def test_the_accepted_pass_mints_its_cells_through_the_one_producer():
    import inspect
    source = inspect.getsource(place_pass.run_window_pass)
    assert "local_cells = local_cells_of(audited)" in source
    assert "np.argwhere" not in source


def test_cold_hypothesis_count_is_the_declared_domain():
    _h3_support.assert_measured(
        "cold domain, one c3 page with overhang",
        cold.hypothesis_count((200, 200), (2240, 1536), 1), 16_926_660)
    _h3_support.assert_measured(
        "cold domain, one c3 page without overhang",
        cold.hypothesis_count((200, 200), (2240, 1536), 1,
                               allow_overhang=False), 10_915_268)
    assert cold.hypothesis_count((200, 200), (2240, 1536), 3) == 3 * (
        cold.hypothesis_count((200, 200), (2240, 1536), 1))
    assert cold.hypothesis_count((300, 300), (128, 128), 1,
                                 allow_overhang=False) == 0


def _naive_cold_map(evidence: np.ndarray, mask: np.ndarray,
                    values: np.ndarray, sites: np.ndarray, rot_k: int,
                    min_support: int) -> np.ndarray:
    observed = np.rot90(np.asarray(evidence, np.float64), rot_k)
    keep = np.rot90(np.asarray(mask, bool), rot_k).astype(np.float64)
    parity = pose.parity_mask(sites.shape, (0, 0), 0)
    search_sites = (sites & parity).astype(np.float64)
    signed = np.where(sites, 1.0 - 2.0 * values.astype(np.float64), 0.0)
    signed = signed * search_sites
    kernel = observed * keep
    shape = observed.shape
    patches = np.lib.stride_tricks.sliding_window_view(signed, shape)
    site_patches = np.lib.stride_tricks.sliding_window_view(
        search_sites, shape)
    numerator = np.einsum("ijab,ab->ij", patches, kernel, optimize=True)
    weight = np.einsum("ijab,ab->ij", site_patches, np.abs(observed) * keep,
                       optimize=True)
    support = np.rint(np.einsum("ijab,ab->ij", site_patches, keep,
                                optimize=True)).astype(np.int64)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = numerator / np.sqrt(weight)
    return np.where((support >= min_support) & (weight > 0.0), z, -np.inf)


def test_correlate_patch_finds_the_argmax_of_an_in_file_naive_z_map():
    row = resolve_format_ref(TINY_ROW)
    field = words.ReferenceField(row)
    page = field.page(0)
    size = COLD_FRAGMENT_CELLS
    oy, ox = COLD_ORIGIN_YX
    bits = page.values[oy:oy + size, ox:ox + size].copy()
    mask = np.ones((size, size), bool)
    evidence = (1.0 - 2.0 * bits.astype(np.float32))
    memo = pose.ScoreMemo(field)
    outcome = cold.correlate_patch(
        evidence, bits, mask, field, (0,), 10 ** 9,
        place.E022_SUPPORT_FLOOR_SITES, memo, place.GATE_SEARCH_TRUE,
        place.GATE_VALIDATION_TRUE, place.GATE_RIVAL_DECOY,
        place.GATE_MINIMUM_GAP, place.NEIGHBOR_RADIUS_CELLS,
        allow_overhang=False)
    assert outcome.accepted is True
    assert outcome.reason == "accepted"
    assert outcome.hypotheses == cold.hypothesis_count(
        (size, size), row.cells_yx, 1, allow_overhang=False)
    best = outcome.best
    assert best is not None
    assert (best.page, best.origin_yx, best.rot_k) == (0, (oy, ox), 0)
    naive = tuple(
        _naive_cold_map(evidence, mask, page.values, page.sites, rot_k,
                        place.E022_SUPPORT_FLOOR_SITES)
        for rot_k in range(4))
    peaks = tuple(float(np.max(z)) for z in naive)
    winner_rot = int(np.argmax(peaks))
    peak = np.unravel_index(int(np.argmax(naive[winner_rot])),
                            naive[winner_rot].shape)
    assert winner_rot == 0
    assert (int(peak[0]), int(peak[1])) == (oy, ox)
    assert best.search_mismatch == 0.0
    assert best.validation_mismatch == 0.0


def test_correlate_patch_refuses_a_domain_above_its_budget():
    row = resolve_format_ref(TINY_ROW)
    field = words.ReferenceField(row)
    size = COLD_FRAGMENT_CELLS
    mask = np.ones((size, size), bool)
    outcome = cold.correlate_patch(
        np.zeros((size, size), np.float32), np.zeros((size, size), np.uint8),
        mask, field, (0,), 10, place.E022_SUPPORT_FLOOR_SITES,
        pose.ScoreMemo(field), place.GATE_SEARCH_TRUE,
        place.GATE_VALIDATION_TRUE, place.GATE_RIVAL_DECOY,
        place.GATE_MINIMUM_GAP, allow_overhang=False)
    assert outcome.accepted is False
    assert outcome.reason == "attempt_budget_exceeded"
    assert outcome.best is None


def test_correlate_patch_refuses_a_blank_patch_for_want_of_support():
    row = resolve_format_ref(TINY_ROW)
    field = words.ReferenceField(row)
    size = COLD_FRAGMENT_CELLS
    outcome = cold.correlate_patch(
        np.zeros((size, size), np.float32), np.zeros((size, size), np.uint8),
        np.zeros((size, size), bool), field, (0,), 10 ** 9,
        place.E022_SUPPORT_FLOOR_SITES, pose.ScoreMemo(field),
        place.GATE_SEARCH_TRUE, place.GATE_VALIDATION_TRUE,
        place.GATE_RIVAL_DECOY, place.GATE_MINIMUM_GAP,
        allow_overhang=False)
    assert outcome.accepted is False
    assert outcome.reason == "insufficient_support"


def test_cold_refuses_a_reference_field_whose_sites_move_with_the_page():
    row = resolve_format_ref(TINY_ROW)
    field = words.ReferenceField(row)
    size = COLD_FRAGMENT_CELLS
    forked = words.ReferencePage(
        1, field.page(1).values, ~field.page(1).sites)
    field._pages[1] = forked
    with pytest.raises(ValueError) as excinfo:
        cold.correlate_patch(
            np.ones((size, size), np.float32),
            np.zeros((size, size), np.uint8), np.ones((size, size), bool),
            field, (0, 1), 10 ** 9, place.E022_SUPPORT_FLOOR_SITES,
            pose.ScoreMemo(field), place.GATE_SEARCH_TRUE,
            place.GATE_VALIDATION_TRUE, place.GATE_RIVAL_DECOY,
            place.GATE_MINIMUM_GAP, allow_overhang=False)
    assert "page-invariant" in str(excinfo.value)


# PAGE-DOMAIN W0: H prices the flavour partition, not the declared
# domain. Floors are the tree's own min_support_for(hypothesis_count)
# at WINDOW_CELLS=200 — pin the function, not a matrix's folklore.
COLD_FLOOR_CASES = (
    ("c2-k-r0700@53x37", ((1, 43), (10, 48), (133, 54))),
    ("c3-k-r0550@10x10", ((1, 36), (2621, 55))),
    ("c3-k-r0550@7x7", ((1, 35), (5349, 56))),
)


@pytest.mark.parametrize("ref,rows", COLD_FLOOR_CASES)
def test_cold_floor_is_a_function_of_the_searched_address_space(ref, rows):
    window = (place.WINDOW_CELLS, place.WINDOW_CELLS)
    cells = resolve_format_ref(ref).cells_yx
    for n_pages, floor in rows:
        hypotheses = cold.hypothesis_count(window, cells, n_pages)
        assert place.min_support_for(hypotheses) == floor, (ref, n_pages)


def test_live_partition_prices_its_own_size_not_the_declared_domain():
    domain = tuple(range(10))
    live = frozenset({0})
    partition = place.cold_flavour_pages(
        domain, place.STAGE_COLD_LIVE, live)
    assert partition == (0,)
    cells = resolve_format_ref("c2-k-r0700@53x37").cells_yx
    window = (place.WINDOW_CELLS, place.WINDOW_CELLS)
    assert place.min_support_for(
        cold.hypothesis_count(window, cells, len(partition))) == 43
    assert place.min_support_for(
        cold.hypothesis_count(window, cells, len(domain))) == 48

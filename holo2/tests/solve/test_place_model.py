"""The OR-9 admission algebra, pinned as literals with their derivation.

W0 sub-wave A1 (H4-PLAN §3-W0).  ``place_model`` is a port of v1's
``placement/{model,policy,defaults}.py``, and R4 pins it BEHAVIOURALLY —
so the numbers below are not "whatever the code returns": each is derived
here by hand from the published formula and the carried constants, and
written as a literal with that derivation in a comment.  Importing
``holo`` to cross-check would violate the firewall; the cross-tree
comparison is W0-B's differential harness.

The one derivation everything else stands on, computed once:

    h2(0.08) = -0.08*log2(0.08) - 0.92*log2(0.92) = 0.4021791902022728
    1 - h2(0.08)                                  = 0.5978208097977272
    identifiability_support_floor(H, 0.08) = ceil(log2(H) / 0.5978208…)
"""
from __future__ import annotations

import math

import pytest

from holo2.solve.geometry import LAYOUT_MIN_WINDOW_CELLS
from holo2.solve.place_model import (
    E022_LAYOUT_MIN_WINDOW_CELLS,
    E022_MIN_WINDOW_CELLS, E022_OVERLAP_CELLS, E022_SUBDIVISION_MAX_DEPTH,
    E022_SUPPORT_FLOOR_SITES, E022_WINDOW_CELLS, GATE_MINIMUM_GAP,
    GATE_RIVAL_DECOY, GATE_SEARCH_TRUE, GATE_VALIDATION_TRUE,
    HISTORICAL_E022_GATE, MAX_LOWER_HINTS, OR9_FLOORS, PROVISIONAL_ALPHA,
    PROVISIONAL_CHANNEL_BER_ENVELOPE, PROVISIONAL_SUPPORT_MARGIN_SITES,
    PROVISIONAL_V1_PLACEMENT_POLICY, V1_WHOLEWORD_RIVAL_GATE, AffinePose,
    AttemptBudget, CandidateScore, PilotObservation, PlacementBudgetPolicy,
    PlacementConfig, PlacementDomainEnvelope, PlacementGate, PoseSegment,
    PoseWindow, WordAttemptBudget, admission_datum, hypothesis_count,
    identifiability_support_floor)
from holo2.solve.words import STAGE_A_MIN_VISIBLE_SITES
from holo2.format.fossils import resolve_fossil_spec

# The A4/6 mm rows v1's own registry carries — PRINTED identities, and
# named as such (C4, RULINGS G5, 2026-08-22: a fossil where the subject
# is a real printed row, a v2 id where the test only needs some row).
# Here the subject is a real row twice over: the operational policy's
# derived floors are read at v1's own operational point, and the
# receiver-wide policy id EMBEDS the row ids, so a v2 twin
# (``c2-k-r0700@52x36``) would silently re-pin a lineage identity.
C2_ROW = "c2-r0700@3328x2304"       # 52x36 tiles
C3_ROW = "c3-r0550@2240x1536"       # 35x24 tiles

# words.py:162-164 — a 200x200 window declares 9 slots x 64x64 phases x 4
# orientations.  The Stage-A count is word-grid geometry, so it reaches
# the policy as an argument (see place_model's NOT-PORTED note).
STAGE_A_200 = 9 * 4096 * 4          # 147,456


# ------------------------------------------------------- the derived floor

def test_identifiability_floor_at_the_v1_operational_point() -> None:
    """e026's site-count law, at the BER envelope production declares."""
    ber = PROVISIONAL_CHANNEL_BER_ENVELOPE          # 0.08
    # log2(1024) = 10 exactly; 10 / 0.5978208097977272 = 16.7274… -> 17
    assert identifiability_support_floor(1024, ber) == 17
    # log2(2) = 1; 1 / 0.5978208097977272 = 1.6727… -> 2
    assert identifiability_support_floor(2, ber) == 2
    # 147456 = 2^17 * 1.125, log2 = 17.169925001442312;
    # 17.169925… / 0.5978208… = 28.7210… -> 29
    assert identifiability_support_floor(STAGE_A_200, ber) == 29
    # the real-sheet single-page cold domain (below): log2 = 25.073668…,
    # 25.073668… / 0.5978208… = 41.9420… -> 42
    assert identifiability_support_floor(35_312_324, ber) == 42
    # a domain of one hypothesis identifies itself: the law returns 0 and
    # the E022 measured floor is what admits (see min_support)
    assert identifiability_support_floor(1, ber) == 0
    # BER 0 -> h2 = 0 by the special case -> the bound is ceil(log2(H))
    assert identifiability_support_floor(1024, 0.0) == 10
    assert identifiability_support_floor(35_312_324, 0.0) == 26


def test_the_floor_refuses_what_it_cannot_bound() -> None:
    for domain in (0, -1, True):
        with pytest.raises(ValueError):
            identifiability_support_floor(domain, 0.08)   # type: ignore[arg-type]
    for error in (0.5, 0.75, -0.01, math.nan, math.inf):
        with pytest.raises(ValueError):
            identifiability_support_floor(1024, error)


def test_min_support_is_the_larger_of_the_two_floors() -> None:
    """max(30, identifiability_support_floor(H, BER) + margin)."""
    def budget(hypotheses: int, ber: float = 0.08, margin: int = 0
               ) -> AttemptBudget:
        return AttemptBudget(hypotheses, PROVISIONAL_ALPHA, ber, "unit-test",
                             support_margin_sites=margin)

    # degenerate: floor 0, so the measured E022 floor is the whole answer
    assert budget(1).min_support == E022_SUPPORT_FLOOR_SITES == 30
    # 17 < 30: the identifiability bound is slack at small domains
    assert budget(1024).min_support == 30
    # 42 > 30: at the real-sheet cold domain the derived floor binds
    assert budget(35_312_324).min_support == 42
    # the margin rides the DERIVED term only (42 + 5 = 47 > 30)
    assert budget(35_312_324, margin=5).min_support == 47
    # …and can lift a slack domain over the measured floor (17 + 20 = 37)
    assert budget(1024, margin=20).min_support == 37
    # BER 0 shrinks the derived term (26) back under the measured floor
    assert budget(35_312_324, ber=0.0).min_support == 30


def test_attempt_budget_refusals() -> None:
    with pytest.raises(ValueError):
        AttemptBudget(0, PROVISIONAL_ALPHA, 0.08, "id")
    with pytest.raises(ValueError):
        AttemptBudget(10, 0.0, 0.08, "id")
    with pytest.raises(ValueError):
        AttemptBudget(10, 1.0, 0.08, "id")
    with pytest.raises(ValueError):
        AttemptBudget(10, PROVISIONAL_ALPHA, 0.5, "id")
    with pytest.raises(ValueError):
        AttemptBudget(10, PROVISIONAL_ALPHA, 0.08, "")
    with pytest.raises(ValueError):
        AttemptBudget(10, PROVISIONAL_ALPHA, 0.08, "id",
                      support_margin_sites=-1)
    with pytest.raises(TypeError):
        AttemptBudget(10, PROVISIONAL_ALPHA, 0.08, "id",
                      gate="historical")           # type: ignore[arg-type]
    # v1's default is the HISTORICAL gate; production passes the other one
    assert AttemptBudget(10, PROVISIONAL_ALPHA, 0.08, "id").gate is (
        HISTORICAL_E022_GATE)


# ------------------------------------------------------ the domain algebra

def test_hypothesis_count_is_offsets_x_rot90_x_pages() -> None:
    page, patch = (3328, 2304), (200, 200)
    # overhang: (3328+199) * (2304+199) = 3527 * 2503 = 8,828,081 per
    # rotation, four rotations (the patch is square) = 35,312,324
    assert hypothesis_count(patch, page, 1, allow_overhang=True) == 35_312_324
    assert hypothesis_count(patch, page, 3, allow_overhang=True) == 3 * 35_312_324
    # no overhang: (3328-199) * (2304-199) = 3129 * 2105 = 6,586,545 x 4
    assert hypothesis_count(patch, page, 1, allow_overhang=False) == 26_346_180
    # a non-square patch swaps its axes on the odd rotations:
    # rot 0,2: (1000-100+1)*(500-200+1) = 901*301 = 271,201 each
    # rot 1,3: (1000-200+1)*(500-100+1) = 801*401 = 321,201 each
    assert hypothesis_count((100, 200), (1000, 500), 1,
                            allow_overhang=False) == 2 * 271_201 + 2 * 321_201
    # a patch larger than the page has no fitting position without overhang
    assert hypothesis_count((300, 300), (64, 64), 1,
                            allow_overhang=False) == 0


# -------------------------------------------------------------- the policy

def test_the_operational_policy_resolves_a_real_row() -> None:
    row = resolve_fossil_spec(C2_ROW)
    assert (row.row_id, row.cells_yx) == ("L:c2-r0700@3328x2304",
                                          (3328, 2304))
    budgets, word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        row, (0,), 3, PlacementConfig(), word_hypotheses=STAGE_A_200)

    qid = "candidate/holo-v1-e026+e022/requires-physical-null"
    assert budgets.cold.max_hypotheses == 35_312_324
    assert budgets.cold.qualification_id == f"{qid}/cold"
    assert budgets.cold.min_support == 42          # the derived floor binds
    # local = (2*neighbor_radius_cells + 1)^2 = 7^2
    assert budgets.local.max_hypotheses == 49
    assert budgets.local.qualification_id == f"{qid}/local"
    assert budgets.local.min_support == 30         # floor(49) = 10 < 30
    # lower = local x the hint portfolio actually offered (3 here)
    assert budgets.lower is not None
    assert budgets.lower.max_hypotheses == 147
    assert budgets.lower.qualification_id == f"{qid}/lower"
    # every route carries the production gate, not the historical default
    for attempt in (budgets.cold, budgets.local, budgets.lower):
        assert attempt.gate is V1_WHOLEWORD_RIVAL_GATE
        assert attempt.familywise_false_accept == PROVISIONAL_ALPHA
        assert attempt.max_true_error_rate == PROVISIONAL_CHANNEL_BER_ENVELOPE

    assert word.max_hypotheses == STAGE_A_200
    assert word.qualification_id == (
        "holo-v1/e022-single-word-multi-slot-union-bound")
    assert PROVISIONAL_V1_PLACEMENT_POLICY.policy_id == f"{qid}/kiss-v1"


def test_no_lower_hints_means_no_lower_budget() -> None:
    row = resolve_fossil_spec(C2_ROW)
    budgets, _word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        row, (0,), 0, PlacementConfig(), word_hypotheses=STAGE_A_200)
    assert budgets.lower is None


def test_policy_refusals() -> None:
    row = resolve_fossil_spec(C2_ROW)
    config = PlacementConfig()
    resolve = PROVISIONAL_V1_PLACEMENT_POLICY.resolve
    with pytest.raises(TypeError):
        resolve("c2-r0700", (0,), 0, config,             # type: ignore[arg-type]
                word_hypotheses=STAGE_A_200)
    with pytest.raises(ValueError):                      # empty page domain
        resolve(row, (), 0, config, word_hypotheses=STAGE_A_200)
    with pytest.raises(ValueError):                      # repeated page
        resolve(row, (0, 0), 0, config, word_hypotheses=STAGE_A_200)
    with pytest.raises(ValueError):                      # outside the row
        resolve(row, (7,), 0, config, word_hypotheses=STAGE_A_200)
    with pytest.raises(ValueError):                      # negative hints
        resolve(row, (0,), -1, config, word_hypotheses=STAGE_A_200)
    with pytest.raises(TypeError):                       # not the exact type
        resolve(row, (0,), 0, "default",                 # type: ignore[arg-type]
                word_hypotheses=STAGE_A_200)


def test_the_receiver_wide_envelope_unions_every_row() -> None:
    rows = ((resolve_fossil_spec(C3_ROW), (0,)),
            (resolve_fossil_spec(C2_ROW), (0,)))
    envelope = PlacementDomainEnvelope.resolve(
        rows, PlacementConfig(), word_hypotheses_per_row=STAGE_A_200)
    # sorted by row id, whatever order the caller offered them in
    assert envelope.row_ids == ("L:c2-r0700@3328x2304",
                                "L:c3-r0550@2240x1536")
    # 35,312,324 (c2 above) + 4 * 2439 * 1735 = 16,926,660 (c3-r0550,
    # 2240x1536 cells) = 52,238,984
    assert envelope.cold_hypotheses == 35_312_324 + 16_926_660 == 52_238_984
    assert envelope.local_hypotheses == 49 * 2
    assert envelope.lower_hypotheses == 49 * MAX_LOWER_HINTS * 2 == 784
    assert envelope.word_hypotheses == STAGE_A_200 * 2
    # The policy id EMBEDS the row ids, so it moved with the ``L:``
    # marker (C2, RULINGS G1) — a lineage identity change, and the
    # reason the row ids are goldens in ``test_format_lattice.py``.
    assert envelope.policy_id == (
        "holo/e022-receiver-wide-domain/kiss-v1/"
        "rows=L:c2-r0700@3328x2304,L:c3-r0550@2240x1536")

    budgets, word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        resolve_fossil_spec(C2_ROW), (0,), 3, PlacementConfig(),
        word_hypotheses=STAGE_A_200, domain_envelope=envelope)
    # the branch searches its own domain but ADMITS against the union:
    # log2(52,238,984) = 25.6384…, / 0.5978208… = 42.8867… -> 43
    assert budgets.cold.max_hypotheses == 52_238_984
    assert budgets.cold.min_support == 43
    assert budgets.cold.qualification_id.endswith(f"/cold/{envelope.policy_id}")
    assert word.max_hypotheses == STAGE_A_200 * 2
    assert word.qualification_id.endswith(f"/{envelope.policy_id}")


def test_an_envelope_that_does_not_cover_the_row_is_refused() -> None:
    row = resolve_fossil_spec(C2_ROW)
    short = PlacementDomainEnvelope(
        ("L:c2-r0700@3328x2304",), 1, 49, 392, STAGE_A_200)
    with pytest.raises(ValueError, match="does not cover"):
        PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
            row, (0,), 3, PlacementConfig(), word_hypotheses=STAGE_A_200,
            domain_envelope=short)
    foreign = PlacementDomainEnvelope(
        ("c3-r0550@2240x1536",), 52_238_984, 98, 784, STAGE_A_200 * 2)
    with pytest.raises(ValueError, match="outside the receiver-wide domain"):
        PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
            row, (0,), 3, PlacementConfig(), word_hypotheses=STAGE_A_200,
            domain_envelope=foreign)
    with pytest.raises(ValueError, match="sorted"):
        PlacementDomainEnvelope(
            ("c3-r0550@2240x1536", "c2-r0700@3328x2304"), 1, 1, 1, 1)
    with pytest.raises(ValueError):
        PlacementDomainEnvelope(("row",), 0, 1, 1, 1)
    with pytest.raises(ValueError):
        PlacementDomainEnvelope.resolve(
            (), PlacementConfig(), word_hypotheses_per_row=STAGE_A_200)


# ---------------------------------------------------------------- the gate

def test_the_two_gate_profiles_carry_the_same_bars_and_distinct_ids() -> None:
    bars = (GATE_SEARCH_TRUE, GATE_RIVAL_DECOY, GATE_MINIMUM_GAP,
            GATE_VALIDATION_TRUE)
    assert bars == (0.20, 0.20, 0.08, 0.24)
    for gate in (HISTORICAL_E022_GATE, V1_WHOLEWORD_RIVAL_GATE):
        assert (gate.search_true, gate.rival_decoy, gate.minimum_gap,
                gate.validation_true) == bars
    # the RULE changed at v0.30 (whole-word rival mismatches), so the
    # identity did too, and the historical row stays as the reference
    assert HISTORICAL_E022_GATE.qualification_id == (
        "paperholo/e022-v2/session-gap-gate")
    assert V1_WHOLEWORD_RIVAL_GATE.qualification_id == (
        "holo-v1/e022-v2-wholeword-rival/session-gap-gate")
    assert HISTORICAL_E022_GATE != V1_WHOLEWORD_RIVAL_GATE


def test_gate_refusals() -> None:
    with pytest.raises(ValueError):                  # a bar at chance
        PlacementGate(0.5, 0.2, 0.08, 0.24, "id")
    with pytest.raises(ValueError):                  # a bar at zero
        PlacementGate(0.0, 0.2, 0.08, 0.24, "id")
    with pytest.raises(ValueError):                  # a gap at chance
        PlacementGate(0.2, 0.2, 0.5, 0.24, "id")
    with pytest.raises(ValueError):                  # unnamed provenance
        PlacementGate(0.2, 0.2, 0.08, 0.24, "")
    # a zero gap is legal (bars alone then decide)
    assert PlacementGate(0.2, 0.2, 0.0, 0.24, "id").minimum_gap == 0.0


# --------------------------------------------------------- the word budget

def test_the_word_union_bound_prices_the_declared_stage_a_domain() -> None:
    word = WordAttemptBudget(STAGE_A_200, PROVISIONAL_ALPHA, "unit-test")
    # sum(C(100, i), i=0..13) = 8,322,009,263,697,336 codeword-sphere
    # points, scaled by 2^(18-100): p = 1.7209511801042833e-09
    assert word.single_word_probability == pytest.approx(
        1.7209511801042833e-09, rel=1e-12)
    # 147,456 * p = 2.537645772134572e-04, comfortably under alpha = 1e-3
    assert word.random_union_bound == pytest.approx(
        2.537645772134572e-04, rel=1e-12)
    assert word.random_union_bound < PROVISIONAL_ALPHA
    # a domain 10^6 wide would spend 1.72e-3 > alpha: refused, not trimmed
    with pytest.raises(ValueError, match="exceeds its false-accept spend"):
        WordAttemptBudget(1_000_000, PROVISIONAL_ALPHA, "unit-test")
    # an empty declared domain is legal and spends nothing
    assert WordAttemptBudget(0, PROVISIONAL_ALPHA, "u").random_union_bound == 0.0


# ------------------------------------------------------- the floors table

def test_or9_table_is_the_home_of_every_admission_constant() -> None:
    names = [datum.name for datum in OR9_FLOORS]
    assert len(names) == len(set(names)), "an OR-9 datum is declared twice"
    derived = [datum for datum in OR9_FLOORS if datum.origin == "derived"]
    assert [datum.name for datum in derived] == ["min_support"]
    assert derived[0].value is None, "a derived datum quotes no number"
    for datum in OR9_FLOORS:
        assert datum.source and datum.note
        assert (datum.value is None) == (datum.origin == "derived")

    config = PlacementConfig()
    policy = PROVISIONAL_V1_PLACEMENT_POLICY
    live: dict[str, int | float] = {
        "e022_support_floor_sites": E022_SUPPORT_FLOOR_SITES,
        "familywise_false_accept": policy.familywise_false_accept,
        "max_true_error_rate": policy.max_true_error_rate,
        "support_margin_sites": policy.support_margin_sites,
        "gate_search_true": V1_WHOLEWORD_RIVAL_GATE.search_true,
        "gate_rival_decoy": V1_WHOLEWORD_RIVAL_GATE.rival_decoy,
        "gate_minimum_gap": V1_WHOLEWORD_RIVAL_GATE.minimum_gap,
        "gate_validation_true": V1_WHOLEWORD_RIVAL_GATE.validation_true,
        "window_cells": config.window_cells,
        "overlap_cells": config.overlap_cells,
        "min_window_cells": config.min_window_cells,
        # the layout floor's live binding is the lattice's own default
        # (``geometry.window_starts``); no config knob carries it.
        "layout_min_window_cells": LAYOUT_MIN_WINDOW_CELLS,
        "subdivision_max_depth": E022_SUBDIVISION_MAX_DEPTH,
        "max_lower_hints": MAX_LOWER_HINTS,
        "stage_a_min_visible_sites": STAGE_A_MIN_VISIBLE_SITES,
    }
    assert set(live) == {datum.name for datum in OR9_FLOORS} - {"min_support"}
    for name, value in live.items():
        assert admission_datum(name).value == value, name
    # the carried values themselves, so a silent edit shows up here
    assert (E022_SUPPORT_FLOOR_SITES, E022_WINDOW_CELLS, E022_OVERLAP_CELLS,
            E022_MIN_WINDOW_CELLS, E022_LAYOUT_MIN_WINDOW_CELLS,
            E022_SUBDIVISION_MAX_DEPTH,
            MAX_LOWER_HINTS) == (30, 200, 40, 70, 8, 1, 8)
    assert (PROVISIONAL_ALPHA, PROVISIONAL_CHANNEL_BER_ENVELOPE,
            PROVISIONAL_SUPPORT_MARGIN_SITES) == (1e-3, 0.08, 0)


def test_the_table_names_the_holo2_placeholders_it_retires() -> None:
    """L7b's three self-declared floors, each answered by a row."""
    retired = {name for datum in OR9_FLOORS for name in datum.retires}
    assert "solve.placement_h3bis.SUPPORT_FLOOR = 0.9" in retired
    assert "solve.toys.TOY_SUPPORT_FLOOR = 0.9" in retired
    assert "solve.geometry.MIN_WINDOW_CELLS = 64 (one tile)" in retired
    assert ("solve.geometry.MIN_WINDOW_CELLS = 70 (the subdivision floor,"
            " applied to a clipped layout)") in retired
    assert admission_datum("min_support").retires
    with pytest.raises(KeyError):
        admission_datum("no-such-datum")


def test_provisional_status_is_carried_with_the_defaults() -> None:
    assert PROVISIONAL_V1_PLACEMENT_POLICY.qualification_id.startswith(
        "candidate/")
    assert "requires-physical-null" in (
        PROVISIONAL_V1_PLACEMENT_POLICY.qualification_id)


# ------------------------------------------ the shapes the kernel produces

def test_placement_config_is_the_measured_e022_geometry() -> None:
    config = PlacementConfig()
    assert (config.window_cells, config.overlap_cells) == (200, 40)
    assert config.min_window_cells == 70 and config.subdivide
    assert config.neighbor_radius_cells == 3 and config.allow_overhang
    with pytest.raises(ValueError):
        PlacementConfig(window_cells=15)
    with pytest.raises(ValueError):
        PlacementConfig(window_cells=100, overlap_cells=100)
    with pytest.raises(ValueError):
        PlacementConfig(min_window_cells=0)
    with pytest.raises(ValueError):
        PlacementConfig(aperture_cells=0.0)
    with pytest.raises(ValueError):                  # total < 2 x per-parity
        PlacementConfig(refine_min_total_sites=30,
                        refine_min_sites_per_parity=20)


def test_affine_pose_maps_cells_to_native_pixels() -> None:
    pose = AffinePose((10.0, 20.0), ((6.0, 0.0), (0.0, 6.0)), (0.1, 0.2),
                      6.0, 0.0)
    points = pose.points([[0.0, 0.0], [1.0, 2.0]])
    assert points.tolist() == [[10.0, 20.0], [16.0, 32.0]]
    assert points.dtype.name == "float64"
    with pytest.raises(ValueError):                  # mirrored (det < 0)
        AffinePose((0.0, 0.0), ((0.0, 6.0), (6.0, 0.0)), (0.0, 0.0), 6.0, 0.0)
    with pytest.raises(ValueError):                  # singular
        AffinePose((0.0, 0.0), ((6.0, 6.0), (6.0, 6.0)), (0.0, 0.0), 6.0, 0.0)
    with pytest.raises(ValueError):                  # non-finite geometry
        AffinePose((math.nan, 0.0), ((6.0, 0.0), (0.0, 6.0)), (0.0, 0.0),
                   6.0, 0.0)
    with pytest.raises(ValueError):                  # pitch must be positive
        AffinePose((0.0, 0.0), ((6.0, 0.0), (0.0, 6.0)), (0.0, 0.0), 0.0, 0.0)


def test_the_kernel_record_shapes_are_frozen_data() -> None:
    window = PoseWindow(3, 1, (120, 240), (200, 200), depth=1,
                        support_estimate=4096)
    segment = PoseSegment(
        window,
        AffinePose((0.0, 0.0), ((6.0, 0.0), (0.0, 6.0)), (0.0, 0.0), 6.0, 0.0),
        support_cells=3900, phase_contrast=0.42, pitch_yx_px=(6.0, 6.0),
        orthogonality_error_deg=0.01)
    candidate = CandidateScore(
        page=0, origin_yx=(64, 128), rot_k=0, search_mismatch=0.05,
        validation_mismatch=0.06, search_errors=3, validation_errors=4,
        search_support=800, validation_support=800, soft_z=7.5, passes=True,
        route="word")
    observation = PilotObservation(
        page=0, tile_yx=(1, 2), site_index=17, bit=1, evidence=1.25,
        capture_id="capture-sha")
    assert segment.window.depth == E022_SUBDIVISION_MAX_DEPTH
    assert candidate.passes and observation.capture_id == "capture-sha"
    for frozen in (window, segment, candidate, observation):
        with pytest.raises(Exception):
            frozen.page = 1                          # type: ignore[attr-defined]


def test_the_policy_is_data_and_compares_by_value() -> None:
    twin = PlacementBudgetPolicy(
        qualification_id=PROVISIONAL_V1_PLACEMENT_POLICY.qualification_id,
        familywise_false_accept=PROVISIONAL_ALPHA,
        max_true_error_rate=PROVISIONAL_CHANNEL_BER_ENVELOPE,
        gate=V1_WHOLEWORD_RIVAL_GATE,
        support_margin_sites=0,
        word_familywise_false_accept=PROVISIONAL_ALPHA,
        word_qualification_id=(
            PROVISIONAL_V1_PLACEMENT_POLICY.word_qualification_id))
    assert twin == PROVISIONAL_V1_PLACEMENT_POLICY
    # a changed bar is a changed policy, which is the whole point of the
    # policy being data: the receiver records what it admitted under
    other = PlacementGate(0.2, 0.2, 0.08, 0.24, "other/profile")
    assert PlacementBudgetPolicy(
        qualification_id=twin.qualification_id,
        familywise_false_accept=PROVISIONAL_ALPHA,
        max_true_error_rate=PROVISIONAL_CHANNEL_BER_ENVELOPE,
        gate=other, support_margin_sites=0,
        word_familywise_false_accept=PROVISIONAL_ALPHA,
        word_qualification_id=twin.word_qualification_id) != twin

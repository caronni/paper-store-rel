"""Golden pins for the frozen placement policy row and §5.3 domain table.

RECEIVE-DESIGN §5.3: "a prose table is an explanation, not the source of
numerical truth."  These assertions are that source.  Every value here is a
frozen statistical commitment of the provisional v1 receiver; a mismatch is
a familywise false-accept-budget change and requires a design amendment,
never a test edit.
"""
from __future__ import annotations

import math

import pytest

from holo.format.registry import get_format_row
from holo.receive.placement.defaults import PROVISIONAL_V1_PLACEMENT_POLICY
from holo.receive.placement.model import (
    HISTORICAL_E022_GATE,
    HISTORICAL_MIN_SUPPORT,
    identifiability_support_floor,
)
from holo.receive.placement.model import PlacementConfig
from holo.receive.placement.policy import PlacementDomainEnvelope
from holo.receive.placement.search import hypothesis_count
from holo.receive.words import WordAttemptBudget


K_ROW_IDS = (
    "c2-r0550@3328x2304", "c2-r0700@3328x2304", "c3-r0550@2240x1536")
P_MAX = 0.08

# RECEIVE-DESIGN §5.3 domain table, verified against the registry 2026-07-31.
DOMAIN_TABLE = (
    (49, 30),                       # one same-level local neighborhood
    (392, 30),                      # eight lower hints in one row
    (16_926_660, 41),               # one C3 page, row known
    (35_312_324, 42),               # one C2 page, row known
    (87_551_308, 45),               # page 0 across all three K rows
    (4_943_725_360, 54),            # all 140 pages of one C2 row
    (5_281_117_920, 55),            # all 312 pages of the C3 row
    (15_168_568_640, 57),           # complete three-row discovery envelope
)


def test_historical_gate_row_is_frozen() -> None:
    gate = HISTORICAL_E022_GATE
    assert gate.search_true == 0.20
    assert gate.rival_decoy == 0.20
    assert gate.minimum_gap == 0.08
    assert gate.validation_true == 0.24
    assert gate.qualification_id == "paperholo/e022-v2/session-gap-gate"
    assert HISTORICAL_MIN_SUPPORT == 30


def test_wholeword_rival_gate_row_is_frozen() -> None:
    from holo.receive.placement.model import V1_WHOLEWORD_RIVAL_GATE

    gate = V1_WHOLEWORD_RIVAL_GATE
    assert gate.search_true == 0.20
    assert gate.rival_decoy == 0.20
    assert gate.minimum_gap == 0.08
    assert gate.validation_true == 0.24
    assert gate.qualification_id == (
        "holo-v1/e022-v2-wholeword-rival/session-gap-gate")


def test_provisional_policy_row_is_frozen() -> None:
    policy = PROVISIONAL_V1_PLACEMENT_POLICY
    assert policy.familywise_false_accept == 1e-3
    assert policy.max_true_error_rate == 0.08
    assert policy.support_margin_sites == 0
    assert policy.word_familywise_false_accept == 1e-3
    from holo.receive.placement.model import V1_WHOLEWORD_RIVAL_GATE

    assert policy.gate == V1_WHOLEWORD_RIVAL_GATE
    assert policy.qualification_id == (
        "candidate/holo-v1-e026+e022/requires-physical-null")
    assert policy.word_qualification_id == (
        "holo-v1/e022-single-word-multi-slot-union-bound")


def test_domain_floor_table_matches_design() -> None:
    entropy = -P_MAX * math.log2(P_MAX) - (1 - P_MAX) * math.log2(1 - P_MAX)
    for hypotheses, floor in DOMAIN_TABLE:
        derived = max(
            HISTORICAL_MIN_SUPPORT,
            identifiability_support_floor(hypotheses, P_MAX),
        )
        assert derived == floor, (hypotheses, derived, floor)
        # The closed form the doc states, recomputed independently.
        assert derived == max(
            30, math.ceil(math.log2(hypotheses) / (1.0 - entropy))
        )


def test_registry_reproduces_the_cold_domains() -> None:
    config = PlacementConfig()
    patch = (config.window_cells, config.window_cells)
    c3 = get_format_row("c3-r0550@2240x1536")
    c2 = get_format_row("c2-r0550@3328x2304")
    assert c3.max_pages == 312
    assert c2.max_pages == 140
    per_page_c3 = hypothesis_count(
        patch, tuple(c3.layout.cells_yx), 1, allow_overhang=True)
    per_page_c2 = hypothesis_count(
        patch, tuple(c2.layout.cells_yx), 1, allow_overhang=True)
    assert per_page_c3 == 16_926_660
    assert per_page_c2 == 35_312_324
    assert per_page_c3 * c3.max_pages == 5_281_117_920
    assert per_page_c2 * c2.max_pages == 4_943_725_360

    rows = tuple(
        (get_format_row(row_id), tuple(range(get_format_row(row_id).max_pages)))
        for row_id in K_ROW_IDS
    )
    envelope = PlacementDomainEnvelope.resolve(rows, config)
    assert envelope.cold_hypotheses == 15_168_568_640
    assert envelope.local_hypotheses == 147
    assert envelope.lower_hypotheses == 1176

    page0 = tuple((spec, (0,)) for spec, _pages in rows)
    assert PlacementDomainEnvelope.resolve(
        page0, config).cold_hypotheses == 87_551_308


def test_resolved_budgets_carry_the_frozen_floors() -> None:
    config = PlacementConfig()
    c3 = get_format_row("c3-r0550@2240x1536")
    budgets, word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        c3, tuple(range(c3.max_pages)), 0, config)
    assert budgets.cold.max_hypotheses == 5_281_117_920
    assert budgets.cold.min_support == 55
    assert budgets.local.max_hypotheses == 49
    assert budgets.local.min_support == 30
    assert budgets.lower is None
    assert word is not None


def test_word_alpha_ceiling_is_exact() -> None:
    exact = math.ldexp(
        sum(math.comb(100, i) for i in range(14)), 18 - 100)
    budget = WordAttemptBudget(16_384, 1e-3, "pin")
    assert budget.single_word_probability == exact
    assert exact == 1.7209511801042833e-09
    WordAttemptBudget(581_074, 1e-3, "pin")
    with pytest.raises(ValueError):
        WordAttemptBudget(581_075, 1e-3, "pin")


def test_route_domain_report_exposes_frozen_floors(tmp_path) -> None:
    """RECEIVE-DESIGN §5.3: the report is the executable domain exposure."""
    from holo.receive.diag import ReceiveDiagnostics
    from holo.receive.observer import ReceiverQualificationStatus
    from holo.receive.production import ProductionAddress

    c3 = get_format_row("c3-r0550@2240x1536")
    address = ProductionAddress(PROVISIONAL_V1_PLACEMENT_POLICY)
    report = address.route_domain_report(c3, tuple(range(c3.max_pages)))
    assert report["routes"]["cold"] == {
        "hypotheses": 5_281_117_920, "min_support_per_parity": 55}
    assert report["routes"]["local"] == {
        "hypotheses": 49, "min_support_per_parity": 30}
    assert report["routes"]["lower"] == {
        "hypotheses": 392, "min_support_per_parity": 30}
    assert report["routes"]["word"]["hypotheses"] == 147_456
    assert report["gate"]["rival_decoy"] == 0.20
    assert report["max_true_error_rate"] == 0.08

    diagnostics = ReceiveDiagnostics(
        tmp_path / "diag", c3,
        receiver_policy_id="pin",
        page_domain=(0,),
        qualification_status=ReceiverQualificationStatus.PROVISIONAL,
        qualification_notes=("pin",),
        route_domains=report,
    )
    written = diagnostics.finalize(object())
    report_path = [row for row in written if row.name == "report.json"]
    assert report_path
    import json
    published = json.loads(report_path[0].read_text())
    assert published["placement_route_domains"]["routes"]["cold"][
        "min_support_per_parity"] == 55

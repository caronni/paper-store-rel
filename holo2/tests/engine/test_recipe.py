"""The recipe's vocabularies: what a policy may name, and what resolves it.

A recipe is typed data, so the only way it can be wrong is by naming a
gate or a footing selector nothing implements. Unvalidated, both failures
are silent — an unknown gate degrades to "always" and an unknown selector
resolves to no footings, forever. These are the pins that make them loud,
plus the DATA pin that the selector vocabulary is exactly the set the
plane resolves: engine names the strings, ``solve`` resolves them, and the
DAG forbids either side importing the other, so the agreement is asserted
here, in the one place a test may see both.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from holo2.engine.recipe import (COST_PAYLOAD, FOOTING_ALL, FOOTING_COARSEST,
                                 FOOTING_FINER, GATE_ALWAYS, GATE_COUNT_READY,
                                 GATE_EXHAUSTION, Recipe,
                                 RecipeEntry, TASK_CLOSE, TASK_PAYLOAD)
from holo2.engine import recipe as recipe_module
from holo2.solve.plane import SessionPlane
from test_orchestrator import ROW, make_session


class _Footing:
    """The two fields ``SessionPlane.footing_ids`` reads off a footing lane."""

    def __init__(self, footing_id: str, ppc: Fraction) -> None:
        self.footing_id = footing_id
        self.ppc = ppc


class _Capture:
    """One capture with a coarse and a fine lane, and no surveyed regions."""

    footings = (_Footing("f:1/1", Fraction(1)), _Footing("f:2/1", Fraction(2)))
    regions = ()


def test_the_footing_selectors_are_exactly_what_the_plane_resolves(
        tmp_path: Path) -> None:
    with make_session(tmp_path) as session:
        plane = SessionPlane(session.store, session.engine, ROW, (_Capture(),))
        resolved = {selector for selector in
                    (FOOTING_ALL, FOOTING_COARSEST, FOOTING_FINER,
                     "cold", "coarse", "")
                    if plane.footing_ids(selector)}
    assert resolved == {FOOTING_ALL, FOOTING_COARSEST, FOOTING_FINER}


def test_a_work_entry_may_not_name_an_unknown_gate() -> None:
    with pytest.raises(ValueError, match="gate"):
        Recipe("recipe-bad-gate", (
            RecipeEntry(TASK_PAYLOAD, FOOTING_ALL, GATE_COUNT_READY, COST_PAYLOAD),
            RecipeEntry(TASK_CLOSE, FOOTING_ALL, GATE_COUNT_READY, COST_PAYLOAD),
        ))


def test_the_close_entry_may_not_name_a_work_gate() -> None:
    with pytest.raises(ValueError, match="gate"):
        Recipe("recipe-bad-close-gate", (
            RecipeEntry(TASK_PAYLOAD, FOOTING_ALL, GATE_ALWAYS, COST_PAYLOAD),
            RecipeEntry(TASK_CLOSE, FOOTING_ALL, GATE_ALWAYS, COST_PAYLOAD),
        ))


def test_the_work_gate_vocabulary_is_one_value_wide() -> None:
    """2026-08-17: footing progression is priced, so no gate defers work.

    ``quiescent`` was the only other work gate there ever was; with it
    deleted, a work entry has exactly one legal answer, and this is what
    would notice a gate quietly growing back.
    """
    assert recipe_module._WORK_GATES == frozenset({GATE_ALWAYS})


def test_an_entry_may_not_name_an_unknown_footing_selector() -> None:
    with pytest.raises(ValueError, match="footing selector"):
        Recipe("recipe-bad-selector", (
            RecipeEntry(TASK_PAYLOAD, "cold", GATE_ALWAYS, COST_PAYLOAD),
            RecipeEntry(TASK_CLOSE, FOOTING_ALL, GATE_EXHAUSTION, COST_PAYLOAD),
        ))

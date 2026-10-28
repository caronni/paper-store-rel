"""The consult-mode vocabulary, pinned equal from both sides of the wall.

The engine owns the words (consult timing is scheduling) and ``solve``
implements against them without importing the engine — the same
structural seam as the footing selectors, and the same remedy (WP-4/16):
the strings are duplicated across a boundary the DAG forbids importing
across, so a data pin asserts the two vocabularies are one.
"""
from __future__ import annotations

from holo2.engine import orchestrator
from holo2.solve import close


def test_consult_mode_vocabularies_are_identical() -> None:
    assert (orchestrator.CONSULT_OBSERVE, orchestrator.CONSULT_CLOSE,
            orchestrator.CONSULT_FINAL) == (
        close.CONSULT_OBSERVE, close.CONSULT_CLOSE, close.CONSULT_FINAL)


def test_every_engine_mode_is_a_mode_solve_accepts() -> None:
    assert set(close._CONSULT_MODES) == {
        orchestrator.CONSULT_OBSERVE, orchestrator.CONSULT_CLOSE,
        orchestrator.CONSULT_FINAL}

"""Canonical-sigmoid pins (RECEIVE-DESIGN v0.39 clause 5.3, ruling 10.3).

The two-branch sigmoid inside ``detect._solve_offset`` is the
project-canonical sigmoid for every receive path in every encoding. It is
deliberately NOT ``scipy.special.expit`` (measured 1–3 ulp non-identity on
~45% of negative inputs, scipy 1.18.0 / numpy 2.5.1; tolerance-masked by
CTX_ROOT_TOL). These pins freeze:

- the import gate: no ``scipy.special.expit`` (or scipy logistic) reference
  anywhere in ``src/holo/receive`` or ``src/holo/core``;
- the source form: the exact two-branch expressions in ``detect.py``;
- the values: the canonical sigmoid on a fixed probe grid (hex-frozen);
- the ``_solve_offset`` shortcuts: clip-low, clip-high, exact-zero, and one
  bisection-resolved value;
- the measured relationship to legacy: paperholo ``payloaddec.py`` used
  scipy ``expit`` — bit-identical on the non-negative branch, within a few
  ulp on the negative branch.

Any mismatch here is formula drift in the canonical sigmoid, not a
tolerance issue.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np
import pytest

from holo.receive.detect import _solve_offset

_SRC_HOLO = Path(__file__).resolve().parents[2] / "src" / "holo"

_FORBIDDEN_NAMES = frozenset({"expit", "logistic", "log_expit"})
_CALL_SITE = re.compile(r"\b(?:expit|log_expit)\s*\(")


def _canonical_sigmoid(x: np.ndarray) -> np.ndarray:
    """The project-canonical two-branch sigmoid (mirror of detect.py)."""
    x = np.asarray(x, np.float64)
    probability = np.empty_like(x)
    positive = x >= 0
    probability[positive] = 1.0 / (1.0 + np.exp(-x[positive]))
    ex = np.exp(x[~positive])
    probability[~positive] = ex / (1.0 + ex)
    return probability


def test_no_scipy_expit_in_receive_or_core() -> None:
    hits: list[str] = []
    for package in ("receive", "core"):
        for path in sorted((_SRC_HOLO / package).rglob("*.py")):
            source = path.read_text()
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name in _FORBIDDEN_NAMES:
                            hits.append(f"{path}:{node.lineno}: from "
                                        f"{node.module} import {alias.name}")
                elif isinstance(node, ast.Attribute):
                    if node.attr in _FORBIDDEN_NAMES:
                        hits.append(
                            f"{path}:{node.lineno}: attribute {node.attr}")
            for lineno, line in enumerate(source.splitlines(), start=1):
                code = line.split("#", 1)[0]
                if _CALL_SITE.search(code):
                    hits.append(f"{path}:{lineno}: {line.strip()}")
    assert hits == [], (
        "scipy expit/logistic reference found in src/holo — the two-branch "
        f"sigmoid in detect._solve_offset is canonical (ruling 10.3): {hits}")


def test_detect_source_carries_the_canonical_form() -> None:
    source = (_SRC_HOLO / "receive" / "detect.py").read_text()
    assert "probability[positive] = 1.0 / (1.0 + np.exp(-x[positive]))" in source
    assert "ex = np.exp(x[~positive])" in source
    assert "probability[~positive] = ex / (1.0 + ex)" in source


# Hex-frozen values of the canonical sigmoid, derived by evaluating the
# canonical form (scipy 1.18.0 / numpy 2.5.1 footing, 2026-08-02). Grid
# covers: deep negative (subnormal output), both branches, the x >= 0
# branch boundary, subnormal and near-zero inputs, and saturation.
_PROBE_PINS: tuple[tuple[float, str], ...] = (
    (-745.0, "0x0.0000000000001p-1022"),
    (-40.0, "0x1.39792499b1a24p-58"),
    (-20.0, "0x1.1b4865556b5d4p-29"),
    (-8.0, "0x1.5fa3dd7d2f7a7p-12"),
    (-2.5, "0x1.36b7112534848p-4"),
    (-1.0, "0x1.136561454ba86p-2"),
    (-0.5, "0x1.829a0565978dfp-2"),
    (-1e-08, "0x1.ffffffd50ce24p-2"),
    (-5e-324, "0x1.0000000000000p-1"),
    (0.0, "0x1.0000000000000p-1"),
    (5e-324, "0x1.0000000000000p-1"),
    (1e-08, "0x1.00000015798eep-1"),
    (0.5, "0x1.3eb2fd4d34391p-1"),
    (1.0, "0x1.764d4f5d5a2bdp-1"),
    (2.5, "0x1.d9291ddb596f8p-1"),
    (8.0, "0x1.ffd40b84505a2p-1"),
    (20.0, "0x1.ffffffee4b79ap-1"),
    (40.0, "0x1.0000000000000p+0"),
    (745.0, "0x1.0000000000000p+0"),
)


def test_canonical_sigmoid_values_pinned() -> None:
    grid = np.array([x for x, _ in _PROBE_PINS])
    values = _canonical_sigmoid(grid)
    got = [float(v).hex() for v in values]
    want = [pin for _, pin in _PROBE_PINS]
    assert got == want


def test_solve_offset_shortcuts_and_bisection_pinned() -> None:
    llr = np.array([-1.25, 0.5, 2.0, -0.75])
    weights = np.ones(4)
    # Clip shortcuts at the CTX_OFFSET_LIMIT rails.
    assert _solve_offset(llr, np.array([True] * 4), weights) == 4.0
    assert _solve_offset(llr, np.array([False] * 4), weights) == -4.0
    # Exact derivative(0) == 0 shortcut (symmetric logits, split labels).
    assert _solve_offset(np.array([-1.5, 1.5]), np.array([False, True]),
                         np.ones(2)) == 0.0
    # Bisection-resolved value through the canonical sigmoid (hex-frozen).
    mixed = _solve_offset(llr, np.array([True, False, True, False]), weights)
    assert float(mixed).hex() == "-0x1.06903cf288000p-4"


def test_legacy_paperholo_used_scipy_expit_and_is_ulp_close() -> None:
    """Divergence-register pin: legacy used scipy expit, holo does not.

    paperholo ``payloaddec.py`` solves the same block offset through
    ``scipy.special.expit``. The canonical form is bit-identical to it on
    the non-negative branch and within a few ulp on the negative branch
    (measured max 3 ulp); actually differing on a large share of negative
    inputs. Canonical-by-fiat: holo keeps the two-branch form.
    """
    payloaddec = pytest.importorskip("paperholo.payloaddec")
    expit = pytest.importorskip("scipy.special").expit
    assert "expit" in dir(payloaddec) or "expit" in (
        Path(payloaddec.__file__).read_text())

    grid = np.array([x for x, _ in _PROBE_PINS])
    ours = _canonical_sigmoid(grid)
    legacy = expit(grid)
    nonneg = grid >= 0
    # Non-negative branch: bit-identical.
    assert np.array_equal(ours[nonneg], legacy[nonneg])
    # Negative branch: never further apart than 4 ulp of our value.
    gap_ulp = np.abs(ours[~nonneg] - legacy[~nonneg]) / np.spacing(
        np.abs(ours[~nonneg]))
    assert float(gap_ulp.max()) <= 4.0

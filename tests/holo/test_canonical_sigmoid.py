"""Canonical-sigmoid pins (RECEIVE-DESIGN v0.39 clause 5.3, ruling 10.3).

Gate E rewrite: the receiver half is gone with `receive.detect`; the law
that survives is the sigmoid itself, so the pinned values are now read
off `holo.receiver.lib.pava.sigmoid` — the production canonical form — and the
import ban is narrowed to `src/holo/core` (holo3's own tree is swept by
src/holo/receiver/tests/test_h3_lib_pava.py).

The project-canonical sigmoid is deliberately NOT
``scipy.special.expit`` (measured 1–3 ulp non-identity on ~45% of
negative inputs, scipy 1.18.0 / numpy 2.5.1; tolerance-masked by the
context root tolerance). These pins freeze:

- the import gate: no ``scipy.special.expit`` (or scipy logistic)
  reference anywhere in ``src/holo/core``;
- the values: the canonical sigmoid on a fixed probe grid (hex-frozen),
  on the written-out form AND on the production one.

The ulp comparison against legacy paperholo's scipy ``expit`` was
deleted 2026-09-20: it pinned third-party behaviour no consumer here
reads, and the measured divergence it recorded is in the paragraph
above, where the ruling lives.

Any mismatch here is formula drift in the canonical sigmoid, not a
tolerance issue.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np

from holo.receiver.lib import pava

_SRC_HOLO = Path(__file__).resolve().parents[2] / "src" / "holo"

_FORBIDDEN_NAMES = frozenset({"expit", "logistic", "log_expit"})
_CALL_SITE = re.compile(r"\b(?:expit|log_expit)\s*\(")


def _canonical_sigmoid(x: np.ndarray) -> np.ndarray:
    """The project-canonical two-branch sigmoid, written out."""
    x = np.asarray(x, np.float64)
    probability = np.empty_like(x)
    positive = x >= 0
    probability[positive] = 1.0 / (1.0 + np.exp(-x[positive]))
    ex = np.exp(x[~positive])
    probability[~positive] = ex / (1.0 + ex)
    return probability


def test_no_scipy_expit_in_core() -> None:
    hits: list[str] = []
    for path in sorted((_SRC_HOLO / "core").rglob("*.py")):
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
        "scipy expit/logistic reference found in src/holo/core — the "
        f"two-branch form is canonical (ruling 10.3): {hits}")


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
    want = [pin for _, pin in _PROBE_PINS]
    assert [float(v).hex() for v in _canonical_sigmoid(grid)] == want
    # The production form (`np.where(x >= 0, 1, e^-|x|) / (1 + e^-|x|)`)
    # is the same two branches written once; it must land on the same
    # bits, or one of the two has drifted.
    assert [float(v).hex() for v in pava.sigmoid(grid)] == want

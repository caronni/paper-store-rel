"""The holo2 firewall as a test: no holo/paperholo imports in holo2/.

Copy-and-adapt, never import (holo2/README.md). ``holo\\b`` does not
match ``holo2`` (no word boundary before the digit), so holo2's own
imports pass.

The walk covers ``holo2/src`` AND ``holo2/tests``, because the README's
claim is about both: the co-located tests are holo2-only, and the
generator/oracle imports live in the repo-root ``holo2/measure`` + ``tests/holo2_oracles`` trees
instead. That second half used to be convention plus a docstring — a
stray ``from holo import …`` in a unit test would have passed the suite
while making the README false, so the rule the two roots differ by is
enforced mechanically here. B4 also renamed the second root, which used
to be a near-anagram of ``holo2/tests`` — the same two words in the
other order, which made every sentence about "which tests" ambiguous at
a glance. The ``_e2e`` suffix says what that root is FOR, and the two
names no longer read alike.
"""
from __future__ import annotations

import re
from pathlib import Path

from _srctree import SRC, sources

_TESTS = Path(__file__).resolve().parent

_FORBIDDEN = re.compile(
    r"^\s*(?:from|import)\s+(?:holo|paperholo|experiments)\b")


def test_no_forbidden_imports() -> None:
    offenders: list[str] = []
    for root in (SRC.parent, _TESTS):
        for path in sources(root):
            for lineno, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1):
                if _FORBIDDEN.match(line):
                    offenders.append(f"{path}:{lineno}: {line.strip()}")
    assert not offenders, (
        "holo2 firewall violation (copy-and-adapt, never import):\n"
        + "\n".join(offenders))


def test_holo2_imports() -> None:
    import holo2  # noqa: F401

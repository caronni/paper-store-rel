"""Trees and the evidence root — stated once.

Historical record of the local A/B battery (2026-08-31); inputs in the
evidence archive.

This tree's ``src/`` is the holo1 generation arithmetic the ground truth
needs, and its ``src/holo/receiver/`` is the receiver under measurement
(imported normally with ``PYTHONPATH=.``).

READ-ONLY: every capture, archived event log and generated stimulus,
under the EVIDENCE ROOT — ``--evidence-root`` or ``$PAPER_EVIDENCE_ROOT``,
no default — the published evidence archive (``measure/_evidence.py``):
sheet I's captures and emission under :data:`SHEET_I`. The 2026-08-30
overnight harvest's event log the 2026-08-31 runs read is NOT in the
published archive (tier delete); it is looked for under :data:`OVERNIGHT`
and refused by name when absent. ARTIFACTS land in a required ``--out``
(``crops/``, ``runs/``, ``reports/`` under it).
"""
from __future__ import annotations

import sys
from pathlib import Path

from measure import _evidence

#: ``<worktree>/measure/local_ab``.
HERE = Path(__file__).resolve().parent

#: The worktree root — the ``PYTHONPATH=.`` root for ``measure.*``.
WORKTREE = HERE.parent.parent

#: This worktree's ``src`` — the only ``holo`` this package imports.
HOLO1_SRC = WORKTREE / "src"

#: The environment variable that names the evidence root when no
#: ``--evidence-root`` was given (``measure/_evidence.py``).
EVIDENCE_ENV = _evidence.ENV

#: Relative to the evidence root: the 2026-08-30 overnight harvest's
#: event logs, by the record's own name — NOT in the published archive
#: (tier delete: event journals excluded by rule).
OVERNIGHT = Path("holo3-overnight-events")

#: Relative to the evidence root: e033 sheet I, published — its
#: ``captures/`` and its ``emission/`` (the EMITTED payload).
SHEET_I = Path("paper-store-evidence-holo-2026-10/033-xerox-rung-experiments/I")

#: Why a withdrawn input is refused, spelled once.
WITHDRAWN = ("tier delete: the overnight harvest's event journals were "
             "excluded by rule and nothing in the record rebuilds them")

_root: Path | None = None


def use_evidence_root(path: Path | None) -> None:
    """Pin the evidence root for this process (``None`` = the env var)."""
    global _root
    _root = None if path is None else Path(path)


def evidence_root() -> Path:
    """The evidence root, or a refusal that names both ways to give it."""
    return _evidence.resolve(_root, tool="local_ab")


def install_src() -> None:
    """Put this worktree's ``src`` on ``sys.path`` (the only ``holo``)."""
    entry = str(HOLO1_SRC)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def refuse_if_absent(paths: tuple[Path, ...]) -> None:
    """Fail loudly and by name rather than half-way through a battery."""
    _evidence.need(*paths, tool="local_ab")


def refuse_if_withdrawn(path: Path) -> None:
    """A withdrawn input (see :data:`WITHDRAWN`), refused by name when
    it is not at its record path under the root."""
    if not path.exists():
        raise _evidence.withdrawn(str(path), tool="local_ab", why=WITHDRAWN)

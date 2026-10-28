"""Trees, interpreter, scratch — stated once.

This package lives in a WORKTREE of ``paper-store`` whose checkout is a
plain ``main`` checkout, so its own ``src/`` is the holo1 generation
arithmetic the ground truth needs (the ``holo3`` branch's worktree
deletes ~1,600 lines under ``src/holo/receive``; this one does not).
Nothing here writes outside the worktree, and every capture, every
archived event log and every generated stimulus under
``scratch`` is READ-ONLY.

Artifacts land in ``<worktree>/scratch/yask/`` (gitignored).
"""
from __future__ import annotations

import sys
from pathlib import Path

#: ``<worktree>/measure/yask``.
HERE = Path(__file__).resolve().parent

#: The worktree root — the ``PYTHONPATH=.`` root for ``measure.*``.
WORKTREE = HERE.parent.parent

#: This worktree's ``src`` — the only ``holo`` this package imports.
HOLO1_SRC = WORKTREE / "src"

#: Read-only evidence: the archived captures and stimuli.
SCRATCH_IN = Path("scratch")

#: The 2026-08-30 overnight harvest's event logs + certificate maps.
OVERNIGHT = SCRATCH_IN / "holo3-overnight-events"

#: The e033 generation set — payloads and per-cell ground-truth fields.
E033 = SCRATCH_IN / "xerox-v1-20260818"

#: Everything this package writes.
SCRATCH = WORKTREE / "scratch/yask"


def install_src() -> None:
    """Put this worktree's ``src`` on ``sys.path`` (the only ``holo``)."""
    entry = str(HOLO1_SRC)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def refuse_if_absent(paths: tuple[Path, ...]) -> None:
    """Fail loudly and by name rather than half-way through a battery."""
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise SystemExit("yask: required input(s) absent: "
                         + ", ".join(missing))

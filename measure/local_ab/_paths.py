"""Trees, interpreter, artifacts — stated once.

This package lives in a WORKTREE of ``paper-store`` whose checkout is a
plain ``main`` checkout, so its own ``src/`` is the holo1 generation
arithmetic the ground truth needs, and its ``holo3/`` is the receiver
under measurement (imported normally with ``PYTHONPATH=.``).

READ-ONLY: every capture, every archived event log and every generated
stimulus under ``scratch``.

ARTIFACTS land in ``scratch/local-ab/`` by the
lead's instruction for this task (this worktree carries no ``scratch/``).
Nothing here writes anywhere under ``scratch/crop-parity/`` — a battery
owns that tree.
"""
from __future__ import annotations

import sys
from pathlib import Path

#: ``<worktree>/measure/local_ab``.
HERE = Path(__file__).resolve().parent

#: The worktree root — the ``PYTHONPATH=.`` root for ``measure.*``.
WORKTREE = HERE.parent.parent

#: This worktree's ``src`` — the only ``holo`` this package imports.
HOLO1_SRC = WORKTREE / "src"

#: Read-only evidence: the archived captures, harvests and stimuli.
SCRATCH_IN = Path("scratch")

#: The 2026-08-30 overnight harvest's event logs.
OVERNIGHT = SCRATCH_IN / "holo3-overnight-events"

#: The e033 generation set — the EMITTED payload each sheet carries.
E033 = SCRATCH_IN / "xerox-v1-20260818"

#: Everything this package writes.
SCRATCH = SCRATCH_IN / "local-ab"


def install_src() -> None:
    """Put this worktree's ``src`` on ``sys.path`` (the only ``holo``)."""
    entry = str(HOLO1_SRC)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def refuse_if_absent(paths: tuple[Path, ...]) -> None:
    """Fail loudly and by name rather than half-way through a battery."""
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise SystemExit("local_ab: required input(s) absent: "
                         + ", ".join(missing))

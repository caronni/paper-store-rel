"""The two trees, the one environment rule, and the sys.path door.

THE TREE RULE, stated once so no other module has to restate it:

* **holo1 is the MAIN worktree** ``<repo>`` and NOTHING
  else. Its ``src/holo`` is the frozen reference receiver AND the ground
  truth generator; the holo3 worktree's own ``src/holo`` differs (branch
  ``holo3`` deletes ~1,600 lines under ``src/holo/receive``), so importing
  ``holo`` from this tree would silently read a different receiver than
  the one whose certificates we are comparing against. Every ``holo``
  import in this package therefore comes from the main tree, and the
  main tree is READ-ONLY: we run its interpreter and its CLI, and we
  write every artifact into this worktree's ``scratch/``.
* **holo3 is this worktree** ``<checkout>``. Its
  ``holo3`` package is imported normally (``PYTHONPATH=.``).

The two packages have disjoint top-level names, so both live on one
``sys.path`` without conflict. Both trees' interpreters are CPython
3.14 (main ``env/bin/python``, here ``env314t/bin/python``, the
free-threading build).
"""
from __future__ import annotations

import sys
from pathlib import Path

#: This package: ``<worktree>/measure/crop_parity``.
HERE = Path(__file__).resolve().parent

#: The holo3 worktree root (the ``PYTHONPATH=.`` root for ``measure.*``).
WORKTREE = HERE.parent.parent

#: The main worktree — holo1's tree. Read-only for this package.
MAIN_TREE = Path("<repo>")

#: The holo1 receiver CLI and its interpreter (used as a subprocess).
HOLO1_PYTHON = MAIN_TREE / "env/bin/python"
HOLO1_CLI = MAIN_TREE / "confetti.py"
HOLO1_SRC = MAIN_TREE / "src"

#: This worktree's interpreter (used for the holo3-side subprocess).
HOLO3_PYTHON = WORKTREE / "env314t/bin/python"

#: The holo3 parity campaign's record — the case source.
PARITY_DIR = WORKTREE / "_distill/verify/parity"
ACCEPTANCE = WORKTREE / "_distill/verify/acceptance.json"

#: Everything this package writes lands here (gitignored).
SCRATCH = WORKTREE / "scratch/crop-parity"


def install_holo1_src() -> None:
    """Put the MAIN tree's ``src`` on ``sys.path`` (the only ``holo``)."""
    entry = str(HOLO1_SRC)
    if entry not in sys.path:
        sys.path.insert(0, entry)
    stale = str(WORKTREE / "src")
    while stale in sys.path:                        # never this tree's src
        sys.path.remove(stale)


def refuse_if_absent() -> None:
    """Fail loudly and by name rather than half-way through a battery."""
    missing = [str(path) for path in
               (HOLO1_PYTHON, HOLO1_CLI, HOLO1_SRC, PARITY_DIR, ACCEPTANCE)
               if not path.exists()]
    if missing:
        raise SystemExit("crop_parity: required input(s) absent: "
                         + ", ".join(missing))

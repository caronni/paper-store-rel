#!env/bin/python
"""confetti3 — holo3 receiver CLI launcher (self-locating, no install).

Run as ``./confetti3.py`` from the repo root: the relative shebang resolves
against the CWD, which is the point — it picks the project venv rather than
whatever ``python3`` happens to be on PATH, and no console script pollutes
the venv. ``confetti.py`` (holo v1) carries the same shebang for the same
reason.

Equivalent form: ``env/bin/python -m holo3 ...``
"""
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from holo3.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

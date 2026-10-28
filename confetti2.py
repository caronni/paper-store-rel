#!env/bin/python
"""confetti2 — holo2 receiver CLI launcher (self-locating, no install).

Run as ``./confetti2.py`` from the repo root: the relative shebang
resolves against the CWD, which is the point — it picks the project venv
(numpy/scipy/Pillow) rather than whatever ``python3`` happens to be on
PATH, and no console script pollutes the venv. ``confetti.py`` (holo v1)
carries the same shebang for the same reason.

Equivalent form: ``PYTHONPATH=holo2/src env/bin/python -m holo2.cli ...``
"""
import sys
from pathlib import Path

_HOLO2_SRC = str(Path(__file__).resolve().parent / "holo2" / "src")
if _HOLO2_SRC not in sys.path:
    sys.path.insert(0, _HOLO2_SRC)

from holo2.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

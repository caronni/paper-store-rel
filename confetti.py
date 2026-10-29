#!env/bin/python
"""Repo-root wrapper for the holo CLI — run as ./confetti.py from the
repo root (the relative shebang resolves against the CWD,
which is the point: no console script pollutes the venv).

Equivalent forms: env/bin/python src/holo/cli.py ...
                  env/bin/python -m holo.cli ...
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from holo.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

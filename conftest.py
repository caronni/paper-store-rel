"""Repo-root pytest bootstrap: make src/ importable EVERYWHERE.

pyproject's ``pythonpath = ["src"]`` covers in-process imports only; the
golden/format tests regenerate stimuli in SUBPROCESSES (gen_e011/gen_e012
via sys.executable), which inherit os.environ, not pytest's sys.path.
Exporting PYTHONPATH here makes a clean checkout green with no editable
install and no .pth file (KISS ruling: holo/paperholo are not pip
packages; measured incident: 81 of 83 repo test failures on 2026-07-29
were this missing propagation).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC = str((Path(__file__).parent / "src").resolve())
_HOLO2_SRC = str((Path(__file__).parent / "holo2" / "src").resolve())

for _path in (_HOLO2_SRC, _SRC):
    if _path not in sys.path:
        sys.path.insert(0, _path)

_existing = os.environ.get("PYTHONPATH", "")
_parts = _existing.split(os.pathsep) if _existing else []
_missing = [p for p in (_SRC, _HOLO2_SRC) if p not in _parts]
if _missing:
    os.environ["PYTHONPATH"] = os.pathsep.join(_missing + _parts)

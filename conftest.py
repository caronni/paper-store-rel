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

import pytest
from pathlib import Path

_SRC = str((Path(__file__).parent / "src").resolve())

for _path in (_SRC,):
    if _path not in sys.path:
        sys.path.insert(0, _path)

_existing = os.environ.get("PYTHONPATH", "")
_parts = _existing.split(os.pathsep) if _existing else []
_missing = [p for p in (_SRC,) if p not in _parts]
if _missing:
    os.environ["PYTHONPATH"] = os.pathsep.join(_missing + _parts)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config,
                                  items: list[pytest.Item]) -> None:
    """The MODULE is the unit of distribution under ``--dist loadgroup``.

    xdist's loadgroup scheduler gives an UNMARKED test its own scope, so
    modules scatter across the workers and every worker rebuilds the
    session fixtures its share of a module needs.  Measured 2026-09-06 on
    the receiver's slow lane: 51 decode setups for 18 fixtures, 729 s of
    duplicated decode work, 176 s wall against 108 s with modules kept
    whole.  A module's own ``xdist_group`` mark (the paperholo build-
    directory groups) wins; ``tryfirst`` runs this before xdist reads the
    marks.
    """
    if not config.pluginmanager.hasplugin("xdist"):
        return
    # xdist resets ``dist`` to "no" inside a worker and carries the mode as
    # ``option.loadgroup`` instead; the marks are read in the worker.
    if not (getattr(config.option, "loadgroup", False)
            or config.getoption("dist", default="no") == "loadgroup"):
        return
    for item in items:
        if item.get_closest_marker("xdist_group") is None:
            item.add_marker(pytest.mark.xdist_group(item.nodeid.split("::")[0]))

"""measure/h3_repricing.py's tree door, without a decode.

The 2026-10-03 review found the tool inert twice over: ``--tree`` put a
tree's ROOT on ``sys.path`` while ``holo`` lives under ``<tree>/src``,
and the record read ``sys.modules["holo3"]`` — a package gone since the
2026-09-05 move — so a finished decode raised before its record was
written.  These pin the door and the refusal; none of them decodes.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

from holo.receiver.tests import _h3_support

ROOT = _h3_support.WORKTREE_ROOT
TOOL = ROOT / "measure" / "h3_repricing.py"

#: A module spelling of the retired package: ``-m holo3``, ``import
#: holo3``, ``from holo3``, ``sys.modules["holo3"]``.  The record NAME
#: holo3 is free to stay; only the module is gone.
_RETIRED_MODULE = re.compile(
    r"""(["']-m["'],\s*["']holo3["'])|(^\s*(import|from)\s+holo3\b)"""
    r"""|(modules\[\s*["']holo3["']\s*\])""", re.MULTILINE)


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_h3_repricing_tool",
                                                  TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_tree(base: Path) -> Path:
    (base / "src" / "holo" / "receiver").mkdir(parents=True)
    return base


def test_the_tree_door_puts_the_trees_src_first(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    tree = _fake_tree(tmp_path / "tree")
    src = _tool()._load_tree(tree)
    assert src == (tree / "src").resolve()
    assert sys.path[:2] == [str(src), str(tree.resolve())]
    _tool()._load_tree(tree)                       # idempotent, no dupes
    assert sys.path.count(str(src)) == 1


def test_the_tree_door_refuses_a_tree_without_the_receiver(tmp_path,
                                                           monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    with pytest.raises(SystemExit, match="no src/holo/receiver"):
        _tool()._load_tree(tmp_path)


def test_the_receiver_file_is_the_chosen_trees_or_the_tool_refuses(
        tmp_path):
    import holo.receiver

    tool = _tool()
    here = Path(holo.receiver.__file__).resolve()
    assert tool._receiver_file(ROOT / "src") == here
    # holo.receiver is already imported from this worktree: any other
    # tree is refused before a capture is built, naming where it went
    other = _fake_tree(tmp_path / "other") / "src"
    with pytest.raises(SystemExit, match=re.escape(str(here))):
        tool._receiver_file(other)


def test_no_instrument_spells_the_retired_holo3_module():
    hits: list[str] = []
    for path in sorted((ROOT / "measure").rglob("*.py")):
        text = path.read_text()
        for match in _RETIRED_MODULE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            hits.append(f"{path.relative_to(ROOT)}:{line}")
    assert hits == [], hits

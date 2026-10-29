"""The fast static undefined-name guard over src/holo and measure/.

Gate E rewrite: this module was 16 v1-receiver state/session fast pins
plus this pyflakes gate; the receiver pins went with `receive/`, and the
gate — which never needed a receiver, only a tree to walk — stays.
"""
from __future__ import annotations

import ast
import textwrap
import time
from pathlib import Path

from pyflakes.checker import Checker
from pyflakes.messages import UndefinedExport, UndefinedLocal, UndefinedName
import pytest


# ---------------------------------------------------------------------------
# fast static undefined-name guard (pyflakes-F821-class) over all of
# src/holo
#
# 2026-08-20 PLANE-FIELDS W2 (0700596) split color_region_details out of
# runtime.py into the new _production_diagnostics.py; the `channel` import
# its body needed stayed behind.  The module still imported cleanly --
# nothing calls color_region_details except the a4b full-tail arm -- so the
# suite stayed green and the NameError only fired live, mid an hours-long
# decode.  Fixed same-day in c79323f (one added import).  This guard is the
# fast (<2s) net for that whole bug class: an undefined name that only a
# rarely-exercised branch reaches.  Engine: pyflakes (installed,
# requirements.txt / pyproject dev extra) via its Checker on the parsed
# AST.
#
# 2026-08-22 widened (holo2 catch-up, RULINGS.md §D) from UndefinedName
# alone to (UndefinedName, UndefinedExport, UndefinedLocal): measured free
# in this tree (zero new findings) and UndefinedExport is exactly what
# turned up a real bug in holo2's carry of this gate (a stale __all__
# entry naming something never imported).  UnusedImport/RedefinedWhileUnused
# etc. stay out of scope -- they are wide enough to hit existing benign
# code (fixture-shadowing, leftover refactor imports) and are a different,
# weaker problem than "this code will crash if it ever runs".

_STATIC_NAME_CLASSES = (UndefinedName, UndefinedExport, UndefinedLocal)


def _undefined_names(source: str, filename: str) -> list[UndefinedName]:
    tree = ast.parse(source, filename=filename)
    checker = Checker(tree, filename=filename)
    return [message for message in checker.messages
            if isinstance(message, _STATIC_NAME_CLASSES)]


def _undefined_name_args(source: str) -> set[str]:
    return {message.message_args[0]
            for message in _undefined_names(textwrap.dedent(source), "<snippet>")}


def test_undefined_name_checker_semantics_on_inline_snippets() -> None:
    """Pin the pyflakes UndefinedName scoping this guard relies on."""
    # comprehension scopes: iterable + loop variable both resolve.
    assert _undefined_name_args("""
        data = [1, 2, 3]
        result = [x for x in data]
    """) == set()

    # class-body statements see module globals directly.
    assert _undefined_name_args("""
        MOD = 1
        class C:
            w = MOD
    """) == set()

    # ...but a *method* does NOT see the class body as an enclosing scope
    # (real Python scoping): a bare class-attribute reference from inside a
    # method is a genuine NameError and must be flagged.
    assert _undefined_name_args("""
        class C:
            z = 1
            def m(self):
                return z
    """) == {"z"}

    # nested functions resolve enclosing-function bindings (closures)
    # across more than one level.
    assert _undefined_name_args("""
        def outer():
            y = 1
            def inner():
                def innermost():
                    return y
                return innermost
            return inner
    """) == set()

    # TYPE_CHECKING-guarded imports are statically bound (symtable/pyflakes
    # see the import regardless of the runtime guard) and must not flag --
    # this is the exact idiom the two real-tree fixes below now use.
    assert _undefined_name_args("""
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            import os
        def f() -> "os.PathLike":
            pass
    """) == set()

    # walrus assignments bind in the containing (function) scope.
    assert _undefined_name_args("""
        def f():
            if (n := 10) > 5:
                return n
    """) == set()

    # decorators are ordinary references to a module-level name.
    assert _undefined_name_args("""
        def deco(fn):
            return fn
        @deco
        def f():
            pass
    """) == set()

    # `del`: a documented pyflakes conservative spot, not a bug in this
    # checker -- don't overthink it, per the plan.  A name deleted anywhere
    # later in a scope reads as possibly-unbound for every reference in
    # that scope, including one that already executed earlier.
    assert _undefined_name_args("""
        def f():
            x = 1
            del x
            return x
    """) == {"x"}

    # The same mechanism reaches into a closure that runs to completion
    # BEFORE the `del` -- this is the exact shape of the one real-tree
    # finding this guard allowlists below (color_payload.py:359: `crops`
    # is read inside a lambda that _parallel.ordered_map calls and fully
    # consumes, wrapped in `tuple(...)`, three lines before `del crops`).
    assert _undefined_name_args("""
        def f(rows):
            crops = {1: 2}
            base = tuple(
                (lambda row: crops[row])(row) for row in rows)
            del crops
            return base
    """) == {"crops"}


def test_no_undefined_names_across_src_holo() -> None:
    """The fast static undefined-name guard, run for real.

    Self-test first (mandatory): a synthetic module reproducing the
    c79323f shape -- a function body reaching for ``channel.X`` with no
    ``channel`` binding anywhere -- must be flagged with exactly that
    name.  Then the real src/holo tree, which must come back clean modulo
    the one documented pyflakes false positive above.
    """
    landmine = textwrap.dedent("""
        from __future__ import annotations

        from .format.descriptor import FormatSpec

        def color_region_details(spec: FormatSpec) -> str:
            return channel.PLANE_ORDER[0]
    """)
    assert {message.message_args[0]
            for message in _undefined_names(landmine, "<landmine>")} == {"channel"}

    # (relative path, name) -- see the del-closure self-test above for why
    # such a finding can be a pyflakes false positive and not a real bug.
    # The one entry this hatch ever held named receive/color_payload.py;
    # src/holo/receive is gone, so it went with it (2026-09-20).
    allowlist: set[tuple[str, str]] = set()

    import holo
    holo_root = Path(holo.__file__).resolve().parent
    source_paths = tuple(
        path for path in sorted(holo_root.rglob("*.py"))
        if "__pycache__" not in path.parts)

    start = time.perf_counter()
    findings: list[str] = []
    for path in source_paths:
        source = path.read_text(encoding="utf-8")
        relative = str(path.relative_to(holo_root))
        for message in _undefined_names(source, str(path)):
            name = message.message_args[0]
            if (path.name, name) in allowlist:
                continue
            findings.append(
                f"{relative}:{message.lineno} undefined name {name!r}")
    elapsed = time.perf_counter() - start
    print(f"undefined-name sweep: {len(source_paths)} files in "
          f"{elapsed:.3f}s")  # visible with pytest -s; not asserted (perf
                               # varies by machine -- the plan's <2s target
                               # is a report, not a pin).

    assert not findings, findings


def test_no_undefined_names_across_measure_instruments() -> None:
    """The same guard over ``measure/`` — the measurement instruments.

    User ruling 2026-08-21: measurement-instrument code lives in neither
    ``tests/`` nor ``scratch/``, which is how the registration-field
    drivers came to live under ``measure/`` — today ``measure/page_field/``,
    the line that superseded the per-lane fitter.  Nothing
    under ``measure/`` is pytest-collected — it is outside ``testpaths``
    and its entry points cost hours and multi-GB states — which is
    exactly the code the a4b landmine class hides in best: an undefined
    name on a branch nobody takes until the run is four hours old.  This
    sweep is the only automatic check those files get.

    Kept separate from the ``src/holo`` sweep above (its own root, its
    own allowlist) so a finding names which tree it came from.
    """
    measure_root = Path(__file__).resolve().parents[2] / "measure"
    if not measure_root.is_dir():                          # pragma: no cover
        pytest.skip("no measure/ tree in this checkout")
    source_paths = tuple(
        path for path in sorted(measure_root.rglob("*.py"))
        if "__pycache__" not in path.parts)
    assert source_paths, "measure/ has no sources — did the tree move?"

    findings = [
        f"{path.relative_to(measure_root)}:{message.lineno} undefined name "
        f"{message.message_args[0]!r}"
        for path in source_paths
        for message in _undefined_names(
            path.read_text(encoding="utf-8"), str(path))]
    assert not findings, findings

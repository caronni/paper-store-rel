"""The pyflakes undefined-name trust gate, carried from ``src/holo``.

Carries the reasoning of ``tests/holo/test_trust_boundaries.py``'s
``bff847d`` gate (2026-08-20, "trust boundaries: pyflakes undefined-name
gate — and its first two catches"): a moved/split function whose body
still references a name whose *import* did not travel with it imports
cleanly (Python does not check names inside function bodies at import
time) and stays invisible to every behavior pin whose only caller is a
rarely-exercised branch — the src/holo incident was PLANE-FIELDS W2
(0700596) splitting ``color_region_details`` out of ``runtime.py``,
leaving its ``channel`` import behind; the suite stayed green and the
``NameError`` only fired live, mid an hours-long decode (fixed same-day,
``c79323f``). This is a purely static, syntax-tree class of bug, which is
what makes an AST sweep the right instrument rather than more unit tests.

Engine: ``pyflakes.checker.Checker`` run directly on a parsed
``ast.Module`` — no subprocess, no ``pyflakes.api`` wrapper. RULINGS §D
(2026-08-22) widens the filtered class beyond src/holo's
``UndefinedName``-only scope
to ``(UndefinedName, UndefinedExport, UndefinedLocal)`` — measured free in
both trees at ruling time, and ``UndefinedExport`` is what turned up the
real bug this package also fixes
(``holo2/src/holo2/solve/place_sched.py``: ``COLD_COST_PER_RUNG`` named in
``__all__`` but never imported — ``UnusedImport``/``RedefinedWhileUnused``
etc. stay out of scope; they are wide enough to hit existing benign code
(fixture-shadowing, leftover refactor imports) and are a different,
weaker problem than "this code will crash if it ever runs").

Two independent sweeps, each with its own root and its own (currently
empty) allowlist, so a finding names which tree it came from:

- ``holo2/src`` via ``_srctree.sources()`` — the shared walk primitive
  (no sixth ``rglob``; see ``_srctree.py``'s own docstring on why a law
  checked by two algorithms is one algorithm and one latent bug).
- ``holo2/measure``, RECURSIVE (including ``verdicts/``), ALSO via
  ``_srctree.sources(measure_root)`` — ``sources()`` already takes the
  root as its first argument, so this sweep is not a second walk
  algorithm either. Nothing under ``measure/`` is pytest-collected
  (``holo2/measure/README.md``), which is exactly the code the same bug
  class hides in best: an undefined name on a branch nobody takes until
  the run is hours old. This sweep is the only automatic check those
  files get. ``verdicts/`` has its own ``conftest.py`` and is
  deliberately excluded from ordinary collection, but that is a
  pytest-collection concern, not a static-text one — a ``.py`` file
  read as text needs no import, so recursing into it here raises no
  collision.

``tests/holo2_oracles`` is not swept: it already sits under the ``tests``
testpath and is pytest-collected on every run, so a moved-away name there
already fails at collection or call time — it does not hide behind the
"nothing under testpaths reaches this branch" condition this gate exists
for.

Each sweep runs a MANDATORY landmine self-test first, inline in the same
test function, reproducing the ``c79323f`` bug shape by name — a gate
that comes back clean is worthless if it has quietly stopped detecting
anything, so every invocation re-proves the detector works before
trusting its silence. An allowlist entry, if one is ever needed, must
reproduce its false-positive mechanism as a pinned snippet in
``test_undefined_name_checker_semantics_on_inline_snippets`` — a
suppression is an artifact that justifies itself, not a hidden knob.
"""
from __future__ import annotations

import ast
import textwrap
import time

from pyflakes.checker import Checker
from pyflakes.messages import Message, UndefinedExport, UndefinedLocal, UndefinedName

from _srctree import SRC, sources

_CLASSES = (UndefinedName, UndefinedExport, UndefinedLocal)


def _static_name_findings(source: str, filename: str) -> list[Message]:
    tree = ast.parse(source, filename=filename)
    checker = Checker(tree, filename=filename)
    return [message for message in checker.messages
            if isinstance(message, _CLASSES)]


def _finding_args(source: str) -> set[str]:
    return {message.message_args[0]
            for message in _static_name_findings(
                textwrap.dedent(source), "<snippet>")}


def test_undefined_name_checker_semantics_on_inline_snippets() -> None:
    """Pin the pyflakes scoping semantics this gate relies on.

    Carries src/holo's set (``tests/holo/test_trust_boundaries.py``:
    comprehensions, class-body vs. method, closures, ``TYPE_CHECKING``,
    walrus, decorators, ``del``) and adds a ``match``-statement snippet:
    holo2's tree is Python >=3.11, so pattern-matching capture names are
    in scope for this gate the way src/holo's tree (which predates
    ``match`` pins in the carried file) never had to pin.
    """
    # comprehension scopes: iterable + loop variable both resolve.
    assert _finding_args("""
        data = [1, 2, 3]
        result = [x for x in data]
    """) == set()

    # class-body statements see module globals directly.
    assert _finding_args("""
        MOD = 1
        class C:
            w = MOD
    """) == set()

    # ...but a *method* does NOT see the class body as an enclosing scope
    # (real Python scoping): a bare class-attribute reference from inside
    # a method is a genuine NameError and must be flagged.
    assert _finding_args("""
        class C:
            z = 1
            def m(self):
                return z
    """) == {"z"}

    # nested functions resolve enclosing-function bindings (closures)
    # across more than one level.
    assert _finding_args("""
        def outer():
            y = 1
            def inner():
                def innermost():
                    return y
                return innermost
            return inner
    """) == set()

    # TYPE_CHECKING-guarded imports are statically bound (symtable/
    # pyflakes see the import regardless of the runtime guard).
    assert _finding_args("""
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            import os
        def f() -> "os.PathLike":
            pass
    """) == set()

    # walrus assignments bind in the containing (function) scope.
    assert _finding_args("""
        def f():
            if (n := 10) > 5:
                return n
    """) == set()

    # decorators are ordinary references to a module-level name.
    assert _finding_args("""
        def deco(fn):
            return fn
        @deco
        def f():
            pass
    """) == set()

    # `del`: a documented pyflakes conservative spot, not a checker bug --
    # don't overthink it. A name deleted anywhere later in a scope reads
    # as possibly-unbound for every reference in that scope, even one that
    # already executed earlier.
    assert _finding_args("""
        def f():
            x = 1
            del x
            return x
    """) == {"x"}

    # the same mechanism reaches into a closure that runs to completion
    # BEFORE the `del`.
    assert _finding_args("""
        def f(rows):
            crops = {1: 2}
            base = tuple(
                (lambda row: crops[row])(row) for row in rows)
            del crops
            return base
    """) == {"crops"}

    # match-statement capture patterns bind in the containing scope
    # (holo2's tree is >=3.11, so this construct is in scope for the gate).
    assert _finding_args("""
        def f(point):
            match point:
                case (x, y):
                    return x + y
                case _:
                    return 0
    """) == set()

    # ...but a name only referenced from *inside* a case guard/body with
    # no binding anywhere is still a genuine undefined name.
    assert _finding_args("""
        def f(point):
            match point:
                case (a, b):
                    return a + b + c
    """) == {"c"}


def _landmine_source() -> str:
    """The c79323f bug shape, plus the place_sched shape this package fixed.

    ``channel`` reproduces the moved-body bug (``UndefinedName``).
    ``__all__ = ["cold_cost_per_rung"]`` naming a symbol the module never
    binds reproduces ``holo2/src/holo2/solve/place_sched.py``'s
    ``COLD_COST_PER_RUNG`` incident (``UndefinedExport``) -- the class
    RULINGS §D (2026-08-22) widened the gate to catch, and the only class
    that would have caught it. Both must fire every run, or the gate has
    gone blind to exactly the fault it exists to repair.
    """
    return textwrap.dedent("""
        from __future__ import annotations

        from .format.descriptor import FormatSpec

        __all__ = ["cold_cost_per_rung"]

        def color_region_details(spec: FormatSpec) -> str:
            return channel.PLANE_ORDER[0]
    """)


def test_no_undefined_names_across_holo2_src() -> None:
    """The gate over ``holo2/src`` — the primary target.

    Self-test first (mandatory): the landmine module must be flagged with
    exactly the missing name AND the stale ``__all__`` entry, in this
    same run, before the real sweep's silence is trusted -- both classes
    RULINGS §D widened the gate to, re-proved every invocation. Then the
    real tree, which must come back clean (empty allowlist today; see
    the module docstring for what an entry would require).
    """
    assert {message.message_args[0]
            for message in _static_name_findings(
                _landmine_source(), "<landmine>")} == {
                    "channel", "cold_cost_per_rung"}

    allowlist: set[tuple[str, str]] = set()

    source_paths = sources(SRC)
    assert source_paths, "holo2/src has no sources -- did the tree move?"

    start = time.perf_counter()
    findings: list[str] = []
    for path in source_paths:
        source = path.read_text(encoding="utf-8")
        relative = str(path.relative_to(SRC))
        for message in _static_name_findings(source, str(path)):
            name = message.message_args[0]
            if (relative, name) in allowlist:
                continue
            findings.append(
                f"{relative}:{message.lineno} {type(message).__name__} "
                f"{name!r}")
    elapsed = time.perf_counter() - start
    print(f"static-name sweep (holo2/src): {len(source_paths)} files in "
          f"{elapsed:.3f}s")  # visible with pytest -s; not asserted.

    assert not findings, findings


def test_no_undefined_names_across_holo2_measure() -> None:
    """The same gate over ``holo2/measure``, RECURSIVE (incl. ``verdicts/``).

    Nothing under ``measure/`` is pytest-collected (``holo2/measure/
    README.md``; ``verdicts/`` carries its own ``conftest.py`` and runs
    only at wave ends via the dedicated verdicts-gate invocation) -- which
    is exactly the code the c79323f bug class hides in best: an undefined
    name on a branch nobody takes until a multi-hour run reaches it, and
    an ``__all__`` typo that a wave-end-only import never trips. This
    sweep is the only automatic check those files get, so it recurses
    into ``verdicts/`` rather than stopping at the top level the way
    ``test_measure_script_imports_resolve`` does (that check is about
    by-path ``__main__`` scripts specifically; this one reads text, not
    imports, so ``verdicts/``'s separate ``conftest.py`` poses no
    collision here). Walk via ``_srctree.sources()`` (RULINGS §D
    (2026-08-22): "no fifth rglob") -- ``sources()`` takes the root as
    its first argument, so a second root is not a second walk algorithm.
    """
    assert {message.message_args[0]
            for message in _static_name_findings(
                _landmine_source(), "<landmine>")} == {
                    "channel", "cold_cost_per_rung"}

    allowlist: set[tuple[str, str]] = set()

    measure_root = SRC.parent.parent / "measure"
    source_paths = sources(measure_root)
    assert source_paths, "holo2/measure has no sources -- did the tree move?"

    findings = []
    for path in source_paths:
        source = path.read_text(encoding="utf-8")
        relative = str(path.relative_to(measure_root))
        for message in _static_name_findings(source, str(path)):
            name = message.message_args[0]
            if (relative, name) in allowlist:
                continue
            findings.append(
                f"{relative}:{message.lineno} {type(message).__name__} "
                f"{name!r}")

    assert not findings, findings

"""The layering law as data: the dependency DAG, and today's debt.

R0 regrouped ``holo2`` into six packages plus a composition root. This
test is where the shape is enforced, and where every violation that
survived the regroup was written down with the phase that removes it.
**R2 emptied both lists**: the sources obey the DAG with no exceptions at
all. Reading order:

1. :data:`ALLOWED` — the DAG. ``core`` depends on nothing but stdlib and
   numpy; ``format`` and ``capture`` on ``core``; ``solve`` on all three;
   ``engine`` on ``core`` alone; ``diag`` observes anything; ``cli``
   composes everything and is imported by nothing.
2. :data:`EDGE_EXCEPTIONS` — modules reaching a package they must not.
   EMPTY since R2. The list may only ever shrink; adding a row is a
   reviewable diff, exactly like a policy bump.
3. :data:`SURFACE_EXCEPTIONS` — cross-package imports that bypass a
   package ``__init__``. EMPTY since R2: every one of them existed
   because an eager re-export would have closed an import cycle that an
   edge exception created, and there are no edges left to close.

Two structural rules carry no exceptions at all: an underscore module is
package-private, and no module wires another module's globals
(composition happens in ``cli`` only).

The walk, the package rule and the relative-import resolver are shared
with the other top-tier gates (``_srctree.py``): the DAG and the error
taxonomy must agree about what ``from .. import x`` names, and they only
do if one function answers.

Tests obey the same DAG (a ``solve`` test may not import ``engine``
internals), with two documented widenings: any test may attach the
observer (``diag``) and drive the composition root (``cli``), because
that is what a test does. Test files that sit at the top of
``holo2/tests`` are the conventions/firewall/CLI tier and compose freely.

``conftest.py`` is the third: R3 made core generic over a record
REGISTRY, so the tests need a composition root of their own the way
production has ``cli``. It composes every package's families and
re-exports the record vocabulary, which is why a ``core`` test can
exercise the store with a ``TileRecord`` without naming ``holo2.solve``
— the fixture module owns that dependency, exactly like a test's own
fixtures own the printed rows an ``engine`` test schedules over.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from _srctree import PACKAGES, SRC as _SRC, holo2_imports as _imports
from _srctree import package_of as _package_of, sources as _sources

_TESTS = Path(__file__).resolve().parent

# ------------------------------------------------------------------ the DAG

ALLOWED: dict[str, frozenset[str]] = {
    "core": frozenset(),
    "format": frozenset({"core"}),
    "capture": frozenset({"core"}),
    "solve": frozenset({"core", "format", "capture"}),
    "engine": frozenset({"core"}),
    # The observer reads everything and is read by nothing but cli.
    "diag": frozenset({"core", "format", "capture", "solve", "engine"}),
    "cli": frozenset({"core", "format", "capture", "solve", "engine", "diag"}),
}

# module (relative to holo2/src/holo2) -> package it must not import,
# why, and the phase that removes it.  EMPTY: R2 burned the last five
# (all of them ``engine/runtime.py``'s, plus the format->engine cycle its
# format row created).  A new row needs a reason and a burn-down phase.
EDGE_EXCEPTIONS: dict[tuple[str, str], tuple[str, str]] = {}

# module -> target module it imports directly instead of through the
# target package's public surface, with the phase that retires it.
# EMPTY: R2 retired the last four with the cycle that forced them.
SURFACE_EXCEPTIONS: dict[tuple[str, str], tuple[str, str]] = {}


# ------------------------------------------------------------------- the DAG

@pytest.mark.parametrize("path", _sources(_SRC),
                         ids=lambda p: str(p).split("holo2/src/holo2/")[-1])
def test_package_dependencies(path: Path) -> None:
    module = str(path.relative_to(_SRC))
    source = _package_of(path, _SRC)
    for target, _names, node in _imports(path, _SRC):
        parts = target.split(".")
        if len(parts) < 2:
            continue
        target_pkg = parts[1] if parts[1] in PACKAGES else "cli"
        if target_pkg == source:
            continue
        if (module, target_pkg) in EDGE_EXCEPTIONS:
            continue
        assert target_pkg in ALLOWED[source], (
            f"{module}:{node.lineno}: {source} -> {target_pkg} is not a "
            f"declared edge (target {target}). Either fix the dependency "
            f"or add a row to EDGE_EXCEPTIONS with its burn-down phase.")


@pytest.mark.parametrize("path", _sources(_SRC),
                         ids=lambda p: str(p).split("holo2/src/holo2/")[-1])
def test_cross_package_imports_use_the_public_surface(path: Path) -> None:
    """A cross-package import names the package, and a name it exports."""
    import importlib

    module = str(path.relative_to(_SRC))
    source = _package_of(path, _SRC)
    for target, names, node in _imports(path, _SRC):
        parts = target.split(".")
        if len(parts) < 2 or parts[1] == source or parts[1] not in PACKAGES:
            continue
        if (module, target) in SURFACE_EXCEPTIONS:
            continue
        assert len(parts) == 2, (
            f"{module}:{node.lineno}: reaches into {target}; cross-package "
            f"imports go through holo2.{parts[1]}'s public surface")
        surface = set(importlib.import_module(target).__all__)
        for name in names:
            if (module, f"{target}:{name}") in SURFACE_EXCEPTIONS:
                continue
            assert name in surface, (
                f"{module}:{node.lineno}: {name} is not on {target}'s "
                f"__all__ surface")


@pytest.mark.parametrize("path", _sources(_SRC),
                         ids=lambda p: str(p).split("holo2/src/holo2/")[-1])
def test_underscore_modules_are_package_private(path: Path) -> None:
    module = str(path.relative_to(_SRC))
    source = _package_of(path, _SRC)
    for target, names, node in _imports(path, _SRC):
        parts = target.split(".")
        if len(parts) < 2 or parts[1] == source:
            continue
        private = [p for p in parts[2:] if p.startswith("_")]
        private += [n for n in names if n.startswith("_")]
        assert not private, (
            f"{module}:{node.lineno}: {private} is package-private to "
            f"{parts[1]}")


def test_nothing_imports_the_observer_but_cli() -> None:
    offenders = []
    for path in _sources(_SRC):
        source = _package_of(path, _SRC)
        if source in ("diag", "cli"):
            continue
        for target, _names, node in _imports(path, _SRC):
            if target.split(".")[1:2] == ["diag"]:
                offenders.append(f"{path.relative_to(_SRC)}:{node.lineno}")
    assert not offenders, f"diag is read by cli only: {offenders}"


# ------------------------------------------------- no cross-package globals

def test_no_module_writes_another_modules_globals() -> None:
    """Composition happens in cli; nobody reaches into an imported module.

    Scoped to names imported from ``holo2`` itself: what a carried leaf
    does to a third-party module's knobs (``scan.py`` bounds Pillow's
    ``MAX_IMAGE_PIXELS`` around one open) is that leaf's business.
    """
    offenders: list[str] = []
    for path in _sources(_SRC):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bound: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                bound |= {(a.asname or a.name.split(".")[0])
                          for a in node.names
                          if a.name.split(".")[0] == "holo2"}
            elif isinstance(node, ast.ImportFrom):
                if node.level or (node.module or "").split(".")[0] == "holo2":
                    bound |= {(a.asname or a.name) for a in node.names}
        for node in ast.walk(tree):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target] if isinstance(
                           node, (ast.AugAssign, ast.AnnAssign)) else [])
            for target in targets:
                if (isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id in bound):
                    offenders.append(
                        f"{path.relative_to(_SRC)}:{node.lineno}: "
                        f"{target.value.id}.{target.attr} = ...")
    assert not offenders, (
        "module globals are package-private; wire in cli instead:\n"
        + "\n".join(offenders))


def test_public_surfaces_hold_no_mutable_state() -> None:
    """A shared mutable object on a surface is a cross-package global.

    R2 emptied the exemption list this test used to carry: the two format
    truth tables (``CODINGS``, later ``LEGACY_CODINGS``, and ``LADDER``)
    were plain dicts published by convention, and became
    ``MappingProxyType`` — read-only in fact, not by promise. The first
    of the two left the tree entirely at C2 (2026-08-22, RULINGS G1);
    ``LADDER`` remains, and nothing else on any surface is a container.
    """
    import importlib

    offenders: list[str] = []
    for package in PACKAGES:
        module = importlib.import_module(f"holo2.{package}")
        for name in module.__all__:
            value = getattr(module, name)
            if isinstance(value, (list, dict, set, bytearray)):
                offenders.append(f"holo2.{package}.{name}: {type(value)}")
    assert not offenders, f"mutable public surface: {offenders}"


# ------------------------------------------------------------------- tests

_TEST_EXTRA = frozenset({"diag", "cli"})   # observe and compose: any test may

# Where a package's tests may reach past that package's own edges.
# Written out rather than derived, so a source-side debt never silently
# licenses a test-side one. R2 emptied the source lists; what survives
# here is not a source dependency but a FIXTURE one: an engine test drives
# a session, and a session is composed — it needs a printed row to name a
# lineage with (``format``) and a plane plus a provider to schedule over
# (``solve``). Both arrive the way the composition root supplies them, as
# data. ``capture`` retired with ``runtime.py``: no engine test opens a
# pixel any more. Narrowing the rest means engine unit tests grow their
# own stub row and stub close provider — a rewrite of what they assert,
# not a move, so it is named here and left to the round that owns it.
TEST_WIDENING: dict[str, frozenset[str]] = {
    "engine": frozenset({"format", "solve"}),      # fixtures, not sources
}


@pytest.mark.parametrize(
    "path", [p for p in _sources(_TESTS) if p.parent != _TESTS],
    ids=lambda p: str(p).split("holo2/tests/")[-1])
def test_test_tree_obeys_the_same_dag(path: Path) -> None:
    package = path.relative_to(_TESTS).parts[0]
    assert package in PACKAGES, f"{path}: unmirrored test directory"
    allowed = (ALLOWED[package] | {package} | _TEST_EXTRA
               | TEST_WIDENING.get(package, frozenset()))
    for target, _names, node in _imports(path, _TESTS):
        parts = target.split(".")
        if len(parts) < 2:
            continue
        target_pkg = parts[1] if parts[1] in PACKAGES else "cli"
        assert target_pkg in allowed, (
            f"{path.name}:{node.lineno}: a {package} test may not import "
            f"{target}")

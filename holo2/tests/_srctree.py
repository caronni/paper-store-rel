"""One walk of the source tree, one package rule, one import resolver.

The four top-tier gates (conventions, layering, error taxonomy, firewall)
each carried their own ``rglob``, two of them their own ``_package_of``,
and two of them DIVERGENT relative-import resolvers — layering resolved
``from . import a`` to the module ``a``, the taxonomy stopped at the
package. A law checked by two algorithms is one algorithm and one latent
bug, so the walk lives here and the gates say what they mean by it.

Test-side only: nothing here is imported by ``holo2/src``.
"""
from __future__ import annotations

import ast
from pathlib import Path

#: The package tree. ``SRC.parent`` is ``holo2/src``, which is what a gate
#: walks when it means "every module the distribution ships".
SRC = Path(__file__).resolve().parent.parent / "src" / "holo2"

PACKAGES = ("core", "format", "capture", "solve", "engine", "diag")


def sources(root: Path = SRC) -> list[Path]:
    """Every module under ``root``, in a deterministic order."""
    return sorted(root.rglob("*.py"))


def package_of(path: Path, root: Path = SRC) -> str:
    """Which package a module belongs to; the composition root is ``cli``."""
    rel = path.relative_to(root)
    return rel.parts[0] if len(rel.parts) > 1 else "cli"


def holo2_imports(path: Path, root: Path = SRC):
    """Yield ``(target_module, imported_names, node)`` per holo2 import.

    ``target_module`` is always absolute and dotted: a relative import is
    resolved against the importing module's own package, so no caller has
    to reimplement ``node.level``. ``from . import a, b`` yields one entry
    per alias (the alias IS the module), with no imported names.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            if node.module is None:               # from . import a, b
                for alias in node.names:
                    yield _absolute(path, root, node, alias.name), (), node
            else:
                yield (_absolute(path, root, node),
                       tuple(a.name for a in node.names), node)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] == "holo2":
                yield node.module, tuple(a.name for a in node.names), node
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "holo2":
                    yield alias.name, (), node


def import_origins(path: Path, root: Path = SRC) -> dict[str, str]:
    """Local bound name -> the holo2 PACKAGE it was imported from.

    ``from``-imports only: what an ``import holo2.core`` binds is the
    ``holo2`` namespace, which names no package.
    """
    origins: dict[str, str] = {}
    for target, _names, node in holo2_imports(path, root):
        parts = target.split(".")
        if not isinstance(node, ast.ImportFrom) or len(parts) < 2:
            continue
        for alias in node.names:
            origins[alias.asname or alias.name] = parts[1]
    return origins


def _absolute(path: Path, root: Path, node: ast.ImportFrom,
              name: str | None = None) -> str:
    """The dotted holo2 module a relative ``ImportFrom`` names."""
    parts = ("holo2", *path.relative_to(root).parts)[:-1]   # package parts
    if node.level > 1:
        parts = parts[:len(parts) - (node.level - 1)]
    tail = (node.module.split(".") if node.module else []) + (
        [name] if name else [])
    return ".".join((*parts, *tail))

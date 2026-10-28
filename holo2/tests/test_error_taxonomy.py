"""Error taxonomy is public surface (R1 cross-cutting adoption).

The rule: a package DECLARES its exception types on its ``__init__``
surface, and cross-package code catches only declared types. The failure
this prevents is the quiet one — a caller catching a package-private
exception class, which then becomes impossible to rename, or catching
``Exception`` and swallowing an integrity refusal that was meant to kill
the run.

The declared set is DERIVED from each package's ``__all__``: the
exception types on a surface ARE the declared ones, and growing that set
is already a reviewed diff against ``test_surfaces.py``'s pin. A
hand-maintained copy here was a second list that had to agree with the
first, and did not (``core``'s ``RegistryError`` and
``UnknownRecordError`` are documented and exported, and were missing).

What is pinned, then, is the one property no other file carries: every
``except`` clause in ``holo2/src`` that names a type imported from
ANOTHER holo2 package names a declared one.
"""
from __future__ import annotations

import ast
import importlib

from _srctree import PACKAGES, SRC as _SRC, import_origins, package_of, sources


def _declared(package: str) -> frozenset[str]:
    """The exception types ``holo2.<package>`` publishes."""
    module = importlib.import_module(f"holo2.{package}")
    return frozenset(
        name for name in module.__all__
        if isinstance(getattr(module, name), type)
        and issubclass(getattr(module, name), BaseException))


DECLARED: dict[str, frozenset[str]] = {
    package: _declared(package) for package in PACKAGES}


def test_cross_package_handlers_catch_only_declared_types() -> None:
    offenders: list[str] = []
    for path in sources():
        source = package_of(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        origins = import_origins(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler) or node.type is None:
                continue
            for name in _handler_names(node.type):
                package = origins.get(name)
                if package is None or package == source:
                    continue
                if name not in DECLARED.get(package, frozenset()):
                    offenders.append(
                        f"{path.relative_to(_SRC)}:{node.lineno}: catches "
                        f"{name}, which holo2.{package} does not declare")
    assert not offenders, "\n".join(offenders)


def _handler_names(node: ast.expr) -> tuple[str, ...]:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Tuple):
        return tuple(name for item in node.elts
                     for name in _handler_names(item))
    if isinstance(node, ast.Attribute):
        return (node.attr,)
    return ()

from __future__ import annotations

import ast
import sys
from pathlib import Path

from . import engine, store_folds
from .descriptor import KEY_KINDS, PluginDescriptor
from .format.identity import FormatRow

EMPTY = "—"
COLLISION = "*"
ESCALATION = "*n"
STORE_ARG = 0
ORDINAL_ARG = 3
PRICE_WIDTH = 7
NAME_WIDTH = 14
STAGE_WIDTH = 13


def _functions(module: object) -> dict[str, ast.FunctionDef]:
    path = Path(module.__file__)
    tree = ast.parse(path.read_text(), filename=str(path))
    return {node.name: node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)}


def _callee(node: ast.Call) -> str:
    callee = node.func
    if isinstance(callee, ast.Attribute):
        return callee.attr
    if isinstance(callee, ast.Name):
        return callee.id
    return ""


def _key_constants(module: object, entry: str) -> tuple[str, ...]:
    functions = _functions(module)
    pending = [entry]
    seen: set[str] = set()
    found: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        node = functions.get(name)
        if node is None:
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name) and inner.id.startswith("KEY_"):
                found.add(inner.id)
            if isinstance(inner, ast.Call):
                pending.append(_callee(inner))
    return tuple(sorted(getattr(module, name) for name in found))


def read_families(descriptor: PluginDescriptor) -> tuple[str, ...]:
    module = sys.modules[descriptor.reads.__module__]
    return _key_constants(module, descriptor.reads.__name__)


def fold_dispatch() -> dict[str, str]:
    fold = _functions(store_folds)["_fold"]
    table: dict[str, str] = {}
    for node in ast.walk(fold):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Call) or _callee(test) != "isinstance":
            continue
        typed = test.args[1]
        name = (typed.attr if isinstance(typed, ast.Attribute)
                else typed.id)
        returned = node.body[0]
        table[name] = ""
        if isinstance(returned, ast.Return) and isinstance(returned.value,
                                                           ast.Call):
            table[name] = _callee(returned.value)
    return table


def write_families(fold_method: str) -> tuple[str, ...]:
    return (_key_constants(store_folds, fold_method)
            if fold_method else ())


def ordinal_names(node: ast.FunctionDef) -> set[str]:
    """The names that stand for a re-run ordinal in one cost function.

    Two shapes, both ordinals. The engine hands one in as argument
    ``ORDINAL_ARG`` — the bookmark's fire count, which suits a row whose
    re-runs and whose expensive work are the same thing. A row whose
    ordinal is DATA it keeps instead (the cell-class law: the mutator
    gatekeeps, the ordinal is a store cell) declares it by binding a
    local name from a read on its ``store`` argument. A price multiplied
    by either escalates, and the ladder must print that.

    Multiplying by a store read INLINE is deliberately not an ordinal:
    that is the shape of a rung premium (``RUNG_COST *
    store.union_rung_ordinal(...)``), which prices a subject, not a
    re-run.
    """
    names = {node.args.args[ORDINAL_ARG].arg}
    store_arg = node.args.args[STORE_ARG].arg
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Assign):
            continue
        if not any(isinstance(sub, ast.Call)
                   and isinstance(sub.func, ast.Attribute)
                   and isinstance(sub.func.value, ast.Name)
                   and sub.func.value.id == store_arg
                   for sub in ast.walk(inner.value)):
            continue
        names |= {target.id for target in inner.targets
                  if isinstance(target, ast.Name)}
    return names


def escalating_prices(descriptor: PluginDescriptor) -> frozenset[int]:
    module = sys.modules[descriptor.cost.__module__]
    node = _functions(module)[descriptor.cost.__name__]
    ordinals = ordinal_names(node)
    found: set[int] = set()
    for inner in ast.walk(node):
        if not isinstance(inner, ast.BinOp):
            continue
        if not isinstance(inner.op, ast.Mult):
            continue
        names = [side.id for side in (inner.left, inner.right)
                 if isinstance(side, ast.Name)]
        if not ordinals.intersection(names):
            continue
        found |= {value for value in
                  (getattr(module, name, None) for name in names)
                  if isinstance(value, int)}
    return frozenset(found)


def price_ladder(
    descriptors: tuple[PluginDescriptor, ...]
) -> tuple[tuple[int, str, str, bool, bool], ...]:
    rows = sorted((price, descriptor.name, stage,
                   price in escalating_prices(descriptor))
                  for descriptor in descriptors
                  for stage, price in descriptor.prices)
    prices = [row[0] for row in rows]
    return tuple((price, name, stage, prices.count(price) > 1, ordinal)
                 for price, name, stage, ordinal in rows)


def _table(header: tuple[str, ...],
           rows: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    widths = [max(len(row[column]) for row in (header,) + rows)
              for column in range(len(header))]
    lines = ["  ".join(cell.ljust(width)
                       for cell, width in zip(header, widths)).rstrip(),
             "  ".join("-" * width for width in widths)]
    for row in rows:
        lines.append("  ".join(cell.ljust(width)
                               for cell, width in zip(row, widths)).rstrip())
    return tuple(lines)


def _joined(names: tuple[str, ...]) -> str:
    return ", ".join(names) if names else EMPTY


def descriptor_rows(
        descriptors: tuple[PluginDescriptor, ...]) -> tuple[str, ...]:
    rows = tuple(
        (descriptor.name, descriptor.subject_kind,
         "|".join(kind.__name__ for kind in descriptor.born_by),
         "|".join(kind.__name__ for kind in descriptor.produces) or EMPTY,
         _joined(read_families(descriptor)))
        for descriptor in descriptors)
    return _table(("name", "subject", "born by", "produces", "reads"),
                  rows)


def ladder_rows(
        descriptors: tuple[PluginDescriptor, ...]) -> tuple[str, ...]:
    ladder = price_ladder(descriptors)
    labels = tuple(f"{price}{ESCALATION}" if ordinal else str(price)
                   for price, _name, _stage, _shared, ordinal in ladder)
    price_width = max(PRICE_WIDTH, *(len(label) for label in labels))
    name_width = max(NAME_WIDTH,
                     *(len(name) + 1 for _p, name, _s, _sh, _o in ladder))
    stage_width = max(STAGE_WIDTH,
                      *(len(stage) + 1 for _p, _n, stage, _sh, _o in ladder))
    return tuple(
        f"{label:>{price_width}}  {name:<{name_width}}"
        f"{stage:<{stage_width}}{COLLISION if shared else ''}".rstrip()
        for label, (_price, name, stage, shared, _ordinal)
        in zip(labels, ladder))


def key_rows(descriptors: tuple[PluginDescriptor, ...]) -> tuple[str, ...]:
    dispatch = fold_dispatch()
    written: dict[str, list[str]] = {kind: [] for kind in KEY_KINDS}
    read: dict[str, list[str]] = {kind: [] for kind in KEY_KINDS}
    for fact_name in sorted(dispatch):
        for kind in write_families(dispatch[fact_name]):
            written[kind].append(fact_name)
    for descriptor in descriptors:
        for kind in read_families(descriptor):
            read[kind].append(descriptor.name)
    rows = tuple(
        (kind, _joined(tuple(written[kind])), _joined(tuple(read[kind])))
        for kind in KEY_KINDS)
    return _table(("family", "written by (fact)", "read by (row)"), rows)


def render(descriptors: tuple[PluginDescriptor, ...] = engine.DESCRIPTORS,
           row: FormatRow | None = None) -> tuple[str, ...]:
    lines: list[str] = []
    if row is not None:
        lines.append(f"format {row.display_id}  family {row.family.name}")
        lines.append("")
    lines.append(f"descriptor rows ({len(descriptors)})")
    lines.extend(descriptor_rows(descriptors))
    lines.append("")
    lines.append(f"price ladder (plugin literals, cheapest first; "
                 f"{COLLISION} = same-price peers; {ESCALATION} = the row "
                 f"re-prices by its own ordinal)")
    lines.extend(ladder_rows(descriptors))
    lines.append("")
    lines.append(f"key families ({len(KEY_KINDS)})")
    lines.extend(key_rows(descriptors))
    return tuple(lines)

"""Immutable format rows available to the discovery-first receiver.

Generation may derive a :class:`~holo.format.descriptor.FormatSpec` from a
printer capability record, but receive-side discovery must not silently grow
or change its hypothesis set when a device note is edited.  This module is
therefore the append-only catalog of complete printed rows which the receiver
is allowed to trial.
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from .descriptor import FormatSpec, get_coding
from .layout import MEDIA_MM


def _row(coding_id: str) -> FormatSpec:
    # All qualified v1 rows presently use the locked A4/6 mm geometry.
    return FormatSpec(
        coding=get_coding(coding_id),
        media_id="a4",
        media_mm=MEDIA_MM["a4"],
        margin_mm=6.0,
    )


def _build_rows(*rows: FormatSpec) -> dict[str, FormatSpec]:
    result: dict[str, FormatSpec] = {}
    for row in rows:
        previous = result.setdefault(row.spec_id, row)
        if previous != row:
            raise ValueError(
                f"format row id {row.spec_id!r} has conflicting semantics")
    return result


FORMAT_ROWS: Mapping[str, FormatSpec] = MappingProxyType(_build_rows(
    _row("c3-r0550"),
    _row("c2-r0550"),
    _row("c2-r0700"),
    _row("c2-cmy7-p120-v0"),
    _row("c3-cmy7-p120-v0"),
    _row("c2-cmy8-p120-v0"),
    _row("c3-cmy8-p120-v0"),
    # Pooled-fountain CMY8 -v1 (docs/CMY8-POOLED-FOUNTAIN.md): catalog
    # only, like every colour row — absent from default discovery.
    _row("c2-cmy8-p120-v1"),
    _row("c3-cmy8-p120-v1"),
))

# Provisional rows belong to the explicit catalog without silently expanding
# cold-start discovery's operational/null budget.
DEFAULT_DISCOVERY_ROW_IDS: tuple[str, ...] = tuple(sorted((
    _row("c3-r0550").spec_id,
    _row("c2-r0550").spec_id,
    _row("c2-r0700").spec_id,
)))


def get_format_row(row_id: str) -> FormatSpec:
    try:
        return FORMAT_ROWS[row_id]
    except KeyError:
        raise KeyError(
            f"unknown format row {row_id!r}; known: "
            f"{sorted(FORMAT_ROWS)}") from None


def registered_format_rows(
    row_ids: tuple[str, ...] | None = None,
) -> tuple[FormatSpec, ...]:
    """Return a canonical, duplicate-free receive hypothesis set."""
    selected = DEFAULT_DISCOVERY_ROW_IDS if row_ids is None else row_ids
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("format row hypotheses must be unique and non-empty")
    rows = tuple(get_format_row(row_id) for row_id in selected)
    return tuple(sorted(rows, key=lambda row: row.spec_id))


__all__ = [
    "DEFAULT_DISCOVERY_ROW_IDS",
    "FORMAT_ROWS",
    "get_format_row",
    "registered_format_rows",
]

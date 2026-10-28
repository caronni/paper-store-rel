"""Small adapters for the E022 known-position BCH promotion firewall."""
from __future__ import annotations

from .placement.model import KnownWord
from .types import BchConflictRecord


def conflict_records(
    words: tuple[KnownWord, ...],
) -> tuple[BchConflictRecord, ...]:
    """Convert final conflicting words into their durable typed audit."""
    output: list[BchConflictRecord] = []
    for row in words:
        if not row.conflict:
            continue
        if row.decoded_counter is None or row.errors is None:
            raise ValueError("conflicting BCH word has no legal decode audit")
        output.append(BchConflictRecord(
            int(row.page), tuple(int(value) for value in row.tile_yx),
            int(row.decoded_counter), int(row.errors), int(row.erasures),
            tuple(row.contributor_patch_ids),
        ))
    return tuple(output)


__all__ = ["conflict_records"]

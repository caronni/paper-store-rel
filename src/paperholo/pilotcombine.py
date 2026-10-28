"""Pure combination of immutable per-scan E022 pilot-search results.

The E022 experiment runner owns persistence and scan ingestion.  This module
owns the reusable, state-free operation at their boundary: rebasing local
region ids, retaining scan provenance, unioning pilot observations by absolute
address, and optionally running the final known-position BCH pass.

Keeping this operation in the library lets integrated receivers compose E022
without importing an experiment CLI or depending on its pickle schema.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

import numpy as np

from paperholo import formats, pilotsearch


@dataclass(frozen=True)
class SearchResultPart:
    """One scan-local result and the region-id extent it occupies.

    ``region_count`` is deliberately explicit.  Unresolved/empty regions do
    not necessarily appear in placements, so deriving the extent from placed
    windows would make the next scan's provenance depend on search success.
    """

    scan_id: str
    region_count: int
    result: pilotsearch.SearchResult


def combine_search_results(
    parts: Iterable[SearchResultPart],
    descriptor: formats.FormatDescriptor,
    *,
    pages: Iterable[int],
    decode_words: bool = True,
) -> pilotsearch.SearchResult:
    """Union scan-local pilot results while retaining scan provenance.

    Every input remains immutable.  Region ids are rebased into one combined
    namespace; placement and observation records are copied with both the
    combined id and their source scan id.  With ``decode_words=True`` the
    union is passed through E022's normal final BCH evaluation.  The false
    branch is for provisional diagnostics: it rolls up already-known source
    tile states without doing work that normally occurs only at scan-final.
    """

    combined = pilotsearch.SearchResult()
    region_base = 0
    timing_total: dict[str, float] = {}
    scan_ids: list[str] = []
    word_states: dict[
        tuple[int, int, int], list[pilotsearch.PilotTileEvidence]
    ] = {}

    for part in parts:
        scan_id = part.scan_id
        region_count = part.region_count
        result = part.result
        scan_ids.append(scan_id)
        region_map = {
            local: region_base + local for local in range(region_count)
        }
        for local, state in result.region_states.items():
            combined.region_states[region_map[int(local)]] = state
        for placement in result.placements:
            diagnostics = dict(placement.diagnostics)
            diagnostics.update({
                "scan_id": scan_id,
                "source_region_index": int(placement.region_index),
            })
            combined.placements.append(replace(
                placement,
                region_index=region_map[int(placement.region_index)],
                scan_id=scan_id,
                diagnostics=diagnostics,
            ))
        for key, tile in result.tiles.items():
            word_states.setdefault(key, []).append(tile)
            target = combined.tiles.get(key)
            if target is None:
                target = pilotsearch.PilotTileEvidence(
                    page=tile.page,
                    tile_y=tile.tile_y,
                    tile_x=tile.tile_x,
                    expected_bits=np.asarray(
                        tile.expected_bits, np.uint8
                    ).copy(),
                )
                combined.tiles[key] = target
            for site_index, observations in tile.observations.items():
                dest = target.observations.setdefault(int(site_index), [])
                for observation in observations:
                    dest.append(replace(
                        observation,
                        region_index=region_map[int(observation.region_index)],
                        scan_id=scan_id,
                    ))
        for key, value in result.timings.items():
            timing_total[key] = timing_total.get(key, 0.0) + float(value)
        region_base += region_count

    if decode_words:
        pilotsearch.decode_known_tiles(
            combined, descriptor.spec(), descriptor.seed
        )
    else:
        for key, source_tiles in word_states.items():
            tile = combined.tiles[key]
            tile.bch_ok = (
                True if any(row.bch_ok is True for row in source_tiles)
                else False if any(row.bch_ok is False for row in source_tiles)
                else None
            )
            tile.bch_attempted = any(
                row.bch_attempted for row in source_tiles
            )
            tile.bch_refused = any(row.bch_refused for row in source_tiles)

    combined.timings = timing_total
    combined.diagnostics = {
        "session_scans": scan_ids,
        "scan_count": len(scan_ids),
        "format_id": descriptor.format_id,
        "pages": list(pages),
    }
    return combined

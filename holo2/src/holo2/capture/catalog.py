"""Attaching a capture BY RECORD — the same facts, without the pixels.

B9 (worklist F-05/D5c, RULED 2026-08-12 "build it"). Before this module a
capture existed to a session only if THIS invocation was handed its file:
``ingest_capture`` was the sole producer of footings and regions, so a
resume re-opened, re-hashed and re-surveyed a 2.29 GB TIFF to learn facts
the store already held — and a resume that was NOT handed the file lost
every footing its durable evidence cites (the F-05 hole).

Nothing here derives a new fact. ``RegionRecord`` v2 already carries the
support grid the survey laid down (origin, step, extent) beside the mask
blob, so :func:`region_from_record` rebuilds the survey's own
``SupportMask`` byte-for-byte, and the two numbers the candidate adds —
its bbox and its area — are functions of that grid and the capture's
declared dpi, exactly as the survey computed them. What the catalog does
is name the inverse direction the H2c carry deliberately dropped.

**The rule, stated where the branch lives (``solve.plane.open_plane``):
an attached capture's FRESH SURVEY WINS over its durable regions.** Ids
are content-derived, so at equal bytes and equal dpi the two agree by
construction; the catalog path is for captures with NO attached raster,
never a second opinion about one that has pixels.

Two things this is deliberately NOT:

* **not a cache.** No pyramid, no derived raster, no bulk anything: a
  facts-only state directory stays facts-only (the ruling's second
  clarification). The only future compute saving on the table is
  skipping a redundant survey re-run when sha and dpi match — measure
  first, and only if attach latency ever hurts.
* **not a re-ingest.** An old capture's evidence is never recomputed.
  Only a NEW file takes the full ingest path; a catalogued capture reads
  its own records and nothing else, and commits nothing.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np

from ..core import CaptureSha, Store
from .ingest import IngestedCapture
from .records import KIND_CAPTURE, KIND_REGION, CaptureRecord, RegionRecord
from .survey import RegionCandidate, SupportMask

#: Native pixels per millimetre, the survey's own conversion (dpi/25.4).
_MM_PER_INCH = 25.4


def region_from_record(record: RegionRecord, cells: np.ndarray,
                       dpi_true: float) -> RegionCandidate:
    """One durable region, back as the candidate the survey produced.

    The inverse of the write in ``ingest_capture``: the mask blob is the
    support grid's cells, the record's three geometry fields are the grid
    it sits on, and ``bbox_px``/``area_mm2`` are read straight off the
    rebuilt :class:`SupportMask` — the same two expressions
    ``survey_raster`` used, over the same values, so a catalogued
    candidate compares equal to the surveyed one.
    """
    support = SupportMask(record.support_origin_px, record.support_step_px,
                          cells, record.support_extent_px)
    px_per_mm = dpi_true / _MM_PER_INCH
    return RegionCandidate(
        capture_sha256=record.capture_sha256,
        support=support,
        pitch_in_vote=record.pitch_in_vote,
        bbox_px=support.bbox,
        area_mm2=support.area_px / (px_per_mm * px_per_mm),
    )


def catalog_capture(record: CaptureRecord,
                    candidates: Iterable[RegionCandidate]) -> IngestedCapture:
    """One capture as the plane sees it, with its raster ABSENT.

    Largest region first, as the survey ordered them (``region_candidates``
    hands back ``survey.regions`` order, which is descending area); ties
    break on the region's own key parts so the tuple index is stable for
    a given store rather than for a given dict iteration.
    """
    ordered = sorted(
        candidates,
        key=lambda candidate: (-candidate.area_mm2, candidate.bbox_px))
    for candidate in ordered:
        if candidate.capture_sha256 != record.source_sha256:
            raise ValueError(
                f"region of capture {candidate.capture_sha256[:12]} offered "
                f"to capture {record.source_sha256[:12]}")
    return IngestedCapture(None, record, tuple(ordered))


def catalog_captures(store: Store, *,
                     attached: Iterable[CaptureSha] = (),
                     select: CaptureSha | None = None,
                     ) -> tuple[IngestedCapture, ...]:
    """Every capture the STORE knows and this invocation was NOT handed.

    Two deterministic passes over the sorted keys — captures first,
    because a region's lattice pitch hangs off its capture's declared dpi
    and a region is only meaningful under its parent. ``attached`` is the
    fresh-survey-wins filter: a capture whose pixels are here is built by
    ingest and is not catalogued beside itself.

    ``select`` narrows the result to ONE capture, and is streaming
    ingestion's door (H4): when the committing thread absorbs a
    capture record it needs exactly that capture's durable form, and
    building it here rather than in the plane is what keeps the inverse
    direction — records back to an ``IngestedCapture`` — in the one
    module that owns it. The walk is unchanged, so the orphan law below
    still runs over the whole store.

    A region whose capture the state holds no record of is REFUSED, not
    skipped: ingest writes the pair in one batch, so an orphan region is
    a corrupt state, and silently dropping it would lose surveyed
    geometry that durable evidence may already cite (L4).
    """
    known = frozenset(attached)
    captures: dict[CaptureSha, CaptureRecord] = {}
    for key in store.keys():
        record = store.get(key)
        if key.kind == KIND_CAPTURE and isinstance(record, CaptureRecord):
            captures[record.source_sha256] = record
    regions: dict[CaptureSha, list[RegionCandidate]] = {}
    for key in store.keys():
        record = store.get(key)
        if key.kind != KIND_REGION or not isinstance(record, RegionRecord):
            continue
        parent = captures.get(record.capture_sha256)
        if parent is None:
            raise ValueError(
                f"{key}: region names capture "
                f"{record.capture_sha256[:12]}, which this state holds no "
                "record of")
        if parent.source_sha256 in known or (
                select is not None and parent.source_sha256 != select):
            continue
        regions.setdefault(parent.source_sha256, []).append(
            region_from_record(record,
                               store.read_array(record.support_mask_ref),
                               parent.dpi_true))
    return tuple(
        catalog_capture(captures[sha], regions.get(sha, ()))
        for sha in sorted(captures)
        if sha not in known and select in (None, sha))


__all__ = ["catalog_capture", "catalog_captures", "region_from_record"]

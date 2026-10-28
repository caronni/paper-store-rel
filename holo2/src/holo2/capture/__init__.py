"""capture — the physical plane: rasters, footings, survey.

Imports: ``core`` (plus stdlib/numpy/scipy and the declared image
decoders). capture opens acquisitions, exposes them as rasters at a
declared footing, measures local lattice pitch, surveys payload regions
and writes the capture facts that follow (``ingest``, R2). It holds no
format knowledge and no scheduling: the cell size a lattice needs is the
printed row's, so lattices and windows are ``solve``'s.

``_survey_tensor`` is package-private: no module outside ``capture`` may
name it (enforced in ``tests/test_layering.py``).

**RECORDS capture owns** (R3, ``records.py``; ``ingest`` is the writer):

* ``CaptureRecord`` (kind ``capture``, **v3**) with ``FootingSpec`` — one
  authenticated acquisition, its platen backing and its derived footing
  ladder, each lane
  naming the capture it is a lane OF (B9's ``FootingView`` collapse).
  Joins the ``captures`` collection.
* ``RegionRecord`` (kind ``region``, **v4**) — one surveyed payload
  region, its support mask, its printed-cell PITCH vote (``pitch_in_vote``,
  a ``Fraction`` since C3 replaced ``c_dots_vote: int`` with it — RULINGS
  G4, 2026-08-22, which is what took the family to v4), its capture parent
  and the support-grid geometry the lattice is laid out on (OR-12). Capture
  plus support grid IS its identity (``region_key``); it carries no id
  field, and the family validates the key against the record.

``attachment_key`` names "this capture's pixels are attached to this
session" (M12) and carries no record. ``scan_key`` names a DECLARED
acquisition input — path plus operator DPI — which is what a streaming
ingest attempt is spent against (H4, 2026-08-17); it carries no record
either.

``catalog`` (B9) is the inverse of ``ingest``: a capture the store
already knows becomes an ``IngestedCapture`` with ``raster=None``, so a
resume needs no pixels to hold its footings, regions and lattices. An
ATTACHED capture is always built by ingest — its fresh survey wins.

**Since streaming ingestion, ingest is WORK, not assembly**:
:class:`IngestWorker` is one declared scan read as an ordinary fire, and
the plane it feeds gets its raster by reopening the file when it absorbs
the capture record.

``footing_raster`` (H4-LANES stage 1) is the ladder's other half: the
SUB-NATIVE rungs, derived directly from the native raster by the carried
``scale_space`` arm and left in the ``<state-dir>.prepared`` sibling under
content-derived names. The ingest fire writes them because it is the fire
that holds the pixels; ``solve`` reads them, and :class:`FootingFrame` is
the one place a coordinate crosses between the native frame a survey is
denominated in and a rung's own.
"""
from __future__ import annotations

from .catalog import catalog_capture, catalog_captures, region_from_record
from .footing_raster import (FootingFrame, FootingPlan, FootingRaster,
                             footing_plan, footing_transform,
                             open_footing_raster)
from .ingest import (FAMILY_INGEST, OUTCOME_INGESTED, ROUTE_SURVEY,
                     IngestedCapture, IngestWorker, footing_raster_for,
                     ingest_capture)
from .records import (KIND_ATTACHMENT, KIND_CAPTURE, KIND_REGION, KIND_SCAN,
                      RECORD_FAMILIES, CaptureRecord, FootingSpec,
                      REGION_KEY_PARTS, RegionRecord, attachment_key,
                      capture_key, parse_region_key, parse_scan_key,
                      region_key, scan_key)
from .scan import Raster, open_capture
from .survey import RegionCandidate, SupportMask

__all__ = [
    # B4 cut this list to what the tree consumes. ``ScaleLevel`` came off
    # in the elegance wave for the reason the rest followed here: a
    # surface pin that advertises a name no caller binds is API kept
    # alive by its own test. Gone with it — all still importable from
    # their own modules, and each rejoins this list in the diff that
    # first imports it from another package —
    # ``survey_raster``, ``region_candidates`` and ``ScaleSchedule`` (the
    # acquisition path runs inside ``ingest``; only its RESULT crosses),
    # ``footing_id_for``, ``COLLECTION_CAPTURES``, and ``LatticeNotFound``
    # (raised and handled inside capture, so it is not a declared
    # cross-package catch — see ``tests/test_error_taxonomy.py``).
    # ``open_capture`` REJOINED with the streaming-ingestion build, which
    # is exactly the diff that clause described: attach-by-reopen is a
    # solve-side act — the plane opens its own handle on the committing
    # thread when it absorbs a capture record — so the acquisition door
    # now crosses the line.
    "Raster", "RegionCandidate", "SupportMask", "open_capture",
    # ingest (R2) + catalog (B9); the family/route/outcome vocabulary and
    # the worker joined with the streaming-ingestion build, when ingest
    # became scheduled work and the composition root grew a provider for
    # it (``solve.ingest``).
    # ``CaptureFacts``/``capture_facts`` stay interior: what crosses a
    # package line is the worker, not the derivation it composes.
    "FAMILY_INGEST", "IngestWorker", "IngestedCapture", "OUTCOME_INGESTED",
    "ROUTE_SURVEY", "ingest_capture",
    "catalog_capture", "catalog_captures", "region_from_record",
    # footing rasters (H4-LANES stage 1): the ladder's sub-native rungs
    # and the frame that maps into one. ``solve`` names all six — the
    # plane opens and derives rungs, and ``prepared`` prepares in a
    # frame — which is exactly the clause the list above describes.
    "FootingFrame", "FootingPlan", "FootingRaster", "footing_plan",
    "footing_raster_for", "footing_transform", "open_footing_raster",
    # records (R3)
    "CaptureRecord", "FootingSpec", "KIND_ATTACHMENT",
    "KIND_CAPTURE", "KIND_REGION", "KIND_SCAN", "RECORD_FAMILIES",
    "REGION_KEY_PARTS", "RegionRecord", "attachment_key", "capture_key",
    "parse_region_key", "parse_scan_key", "region_key", "scan_key",
]

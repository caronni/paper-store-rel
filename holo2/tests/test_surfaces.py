"""Public surfaces, pinned: growing one is a reviewable diff.

Each package's ``__all__`` is frozen here as data. The point is not that
these particular names are right — it is that a name joining or leaving a
package's public surface shows up in a diff next to the reason, instead
of appearing silently the first time somebody imports it from the wrong
place. ``tests/test_layering.py`` enforces that cross-package imports use
these surfaces; this file says what they are.

Rules the pins carry:

* every pinned name resolves (``__all__`` cannot advertise what is not
  there);
* ``holo2`` itself exports nothing: it is a namespace, not a facade —
  callers name the package they depend on.

Duplicates and underscore names need no test of their own: the pin below
is an exact sorted comparison, so either one lands in this file's diff.

**B4 shrank every list here to what the tree actually consumes** (209
pinned names -> 162). The census was mechanical: for each pinned name,
count the importers outside its defining package across ``holo2/src``
and both test roots, counting this pin as no consumer at all. FORTY-EIGHT
had zero and left; ``solve.toys`` left by ruling (a toy scaffold is not
production surface, and it was deleted outright at H4 W1b — H4-PLAN R11)
and ``format.registry_rows`` was replaced by the three functions its four
callers actually reached for.

What that does NOT do is delete anything. A dropped name still lives in
its own module — ``holo2.core.blobs.BlobError`` and
``holo2.solve.plans.RegionView`` import exactly as before, and the tests
that exercise them already name those modules, because a test is not
bound by the cross-package surface law. What it does is stop a package
advertising API that only its own pin keeps alive.

The rule this file now carries: a name joins a surface in the same diff
as the first cross-package import of it. That includes the exception
types — the taxonomy law derives DECLARED from ``__all__``
(``test_error_taxonomy.py``), so a type nobody catches across a package
boundary is not declared, and re-declaring one is a one-line diff at the
handler that needs it.
"""
from __future__ import annotations

import importlib

import pytest

SURFACES: dict[str, tuple[str, ...]] = {
    "holo2": (),
    "holo2.core": (
        # ``digest_json``/``sha256_hex`` left with the B4 census: core's
        # own modules and core's own tests use them, no other package.
        "canonical_json_bytes",
        "StagedBlob", "stage_array", "stage_bytes",
        "CommitBatch", "CommitEngine", "CommitResult",
        "SpendProposal", "Subscription", "Write", "batch_id",
        # ``SpendRecord`` is the ledger's durable row, published so a
        # derived view can COUNT spends (the payload family's CRC
        # exposure) without reaching into ``core.identity``.
        # ``identity_digest`` left with ``MintRef.attempt_digest`` (tile
        # family v3): the ledger row's own values name an attempt.
        "SpendRecord",
        # ``SubjectId`` is off the surface: the subject vocabulary that
        # crosses is ``SubjectSpec`` plus ``KIND_SUBJECT``.
        "CaptureSha", "FootingId", "PoolId", "StreamId",
        "WorkId",
        # keys + the record REGISTRY (R3): core owns the mechanism and two
        # families of its own; every other family belongs to the package
        # that writes it.
        # ``KeySpec`` + ``KeyField``/``KeyEmbed`` are how a package
        # DECLARES a kind's key; ``build_key``/``parse_key`` walk it, so
        # the arity guard lives at the law, not in seven builders.
        # ``KIND_CLOSE``, ``KIND_COLLECTION``, ``subject_key`` and
        # ``subject_collection_key`` left with the B4 census.
        "AttemptIdentity", "BlobRef", "CLOSE_KEY", "CloseRecord",
        "CloseStatus", "KIND_SUBJECT",
        "KeyEmbed", "KeyField", "KeySpec",
        "RECORD_FAMILIES", "Record", "RecordFamily", "RecordRegistry",
        "ResourceKey", "SubjectSpec", "build_key", "collection_key",
        # ``require_own_key`` is F-07's key⇔record check, published
        # because nine families in three packages state that one law.
        "compose", "key_parts", "parse_key", "require_finite_positive",
        "require_own_key", "require_sha256_hex", "require_sorted_unique",
        # the durable-publish primitive and the two cadence defaults: the
        # CLI and the session both RELAY them, so they are core's surface
        # rather than a reach into ``core.store``/``core.trace``.
        # ``JOURNAL_NAME`` joined them for B9 (as ``ENVELOPE_NAME``, the
        # file F-16 abolished): the CLI asks whether a directory holds a
        # session before it insists on a capture, and the authoritative
        # file's name has exactly one owner.
        "DEFAULT_SNAPSHOT_EVERY", "DEFAULT_TRACE_SAMPLE_EVERY",
        "JOURNAL_NAME", "ReplayCursor", "Store", "TraceWriter",
        # H4 W2: the journal's two entry shapes. The ENGINE reads
        # markers back (replay is marker-driven now), so the pair
        # crosses a package boundary and belongs on the surface.
        "is_marker", "marker_work_id",
        "publish_once",
        # ``MAX_WORK_UNITS`` is off the surface: it is ``ProgressSink``'s
        # own default cap and nothing binds it. ``Lease`` left in B4 —
        # ``LeaseBook`` was what the orchestrator held — and CAME BACK at
        # W4, when a solve-side worker first had residency worth
        # declaring (the cold pair's page transforms): the type crosses
        # the boundary now, so it is on the surface again.
        # ``SourceJob``/``WorkSource`` joined at H4 W2: the pull model's
        # second admission shape, implemented in ``solve`` and admitted by
        # ``engine``, so the pair crosses two boundaries.
        "Decline", "ExpansionRequest", "Lease", "LeaseBook",
        "ProgressSink", "Provider", "SolveView", "SourceJob",
        "WorkDescriptor", "WorkResult", "WorkScope", "WorkSource", "Worker",
        "check_progress", "providers_by_family", "providers_identity",
        # error taxonomy (R1): what cross-package code DOES catch. The
        # eight core raises and handles alone — ``BlobError``,
        # ``CodecError``, ``DuplicateWrite``, ``SilentStage``,
        # ``SpendConflict``, ``StoreError``, ``TerminalSessionError``,
        # ``UnknownRecordError`` — left in B4 and rejoin with the first
        # cross-package handler that names one.
        # ``StoreError`` CAME BACK at the C5 review fix (2026-08-22),
        # which is that law firing: ``cli.py`` reads a state directory's
        # identity before owning it (``Store.peek_identity``, journal
        # line 1), so the store's freshness refusals — an older schema, a
        # bare legacy id — now arrive during ARGUMENT CHECKING and must
        # leave as a ``confetti2:`` exit line, not as a traceback. That
        # ``except StoreError`` is the first cross-package handler.
        "CertificateConflict", "CommitRefusal", "MalformedKeyError",
        "ProtocolViolation", "RegistryError", "ReplayError",
        "StateRegression", "StoreError",
    ),
    "holo2.format": (
        # four carried leaves a caller reads MODULE-QUALIFIED.
        # ``registry_rows`` was the fifth and was not one of those: it
        # was published so four call sites could reach a single function
        # apiece, so B4 put those three functions here by name instead.
        # ``ldpc_tile`` stayed a namespace for a hard reason — its one
        # caller is ``solve/tiles.py``, AST-pinned against
        # ``holo.receive.tiles``, so the spelling is part of the carry.
        # ``bch_batch`` joined with the batched Chien card: the twin of a
        # carried leaf, read module-qualified beside it at the one call
        # site (``solve/words.py``) that picks an arm.
        "bch", "bch_batch", "keystream", "ldpc_tile", "pilots",
        # ``Family`` joined at WP-1.1 (2026-08-22) under the same B4
        # law: the first cross-package import is ``solve/close.py``,
        # which asks "is this row K?" to decide whether the counting
        # report labels its per-block rows by stream. It is the ONE
        # legal dispatch key (FORMAT-SPACE P1) and replaces a
        # ``codec_id == "k-v1"`` string compare.
        # ``CODINGS`` became ``LEGACY_CODINGS`` at WP-1.2 and LEFT
        # ENTIRELY at C2 (2026-08-22, RULINGS G1): a legacy coding NAME
        # is not an identity — a printed sheet is named by a whole
        # ``L:`` line, coding AND geometry, matched byte-exactly — so a
        # table of half-names could only build sheets nobody printed.
        # Its one cross-package consumer was ``cli.py``'s ``--coding``
        # choices, which now names a v2 coding id; the legacy route
        # returns as ``--format L:<id>`` with the CLI package (RULINGS
        # G6). ``get_coding`` had already left at WP-1.2.
        # THE GRAMMAR'S DOOR JOINED AT C5 (2026-08-22, RULINGS G6) and
        # ``format_row`` LEFT in the same diff, under the one law in
        # both directions: ``cli.py``'s ``--format`` is the first
        # cross-package importer of ``resolve_format_ref`` /
        # ``ResolvedRef`` / ``format_row_for``, and it was the ONLY
        # cross-package importer of ``format_row`` — which names half an
        # identity (a coding id, with geometry stated separately) that no
        # operator surface spells any more. ``parse_format_id`` stays
        # off: outside ``format`` a reference is RESOLVED, never parsed.
        # Net +2. ``format_row`` itself is untouched in
        # ``registry_rows``, where the callers that mean to take a
        # coding and a grid apart live; a test is not bound by the
        # cross-package surface law.
        "Family", "FormatRowSpec", "LADDER",
        "METADATA_BITS_PER_TILE", "ResolvedRef",
        "STREAM_MAIN", "TILE_CELLS", "TileFormat",
        "format_row_for", "native_cell_pitch_px", "resolve_format_ref",
        "tile_format_for",
        "CertifiedStreamSymbol", "CloseResult", "CloseSpec",
        "close_count_ready", "close_record_from_result",
        "close_volume", "metadata_from_certificates",
        # the incremental close gate's dependencies (P3-1, 2026-08-13):
        # the metadata equation algebra and the ONE authoritative
        # ESI-to-block mapping, consumed by ``solve/close.py``.
        "METADATA_WORD_BITS", "MIN_METADATA_EQUATIONS", "MetadataDecode",
        "SUPPORTED_METADATA_VERSIONS", "VolumeCode", "coefficient_mask",
        "decode_metadata", "volume_code_for",
        # no error taxonomy: format's four integrity refusals are raised
        # and handled inside format (B4).
    ),
    "holo2.capture": (
        # ``ScaleLevel`` is off the surface: it types a ``ScaleSchedule``
        # row and no caller outside ``scale_space`` names it. B4 took
        # ``ScaleSchedule`` itself the same way, with
        # ``survey_raster``, ``region_candidates`` and ``footing_id_for``
        # — the acquisition path runs inside ``ingest``, and only its
        # RESULT crosses a package line. ``open_capture`` REJOINED with
        # the streaming-ingestion build: attach-by-reopen is the plane's
        # own act, so the acquisition door itself crosses now.
        "Raster", "RegionCandidate",
        "SupportMask", "open_capture",
        # ingest, plus the family vocabulary streaming ingestion needs on
        # the surface (H4): the composition root's provider mints an
        # ``IngestWorker`` for family ``FAMILY_INGEST`` on
        # ``ROUTE_SURVEY``. ``CaptureFacts``/``capture_facts`` stay
        # interior — the derivation is composed, never crossed.
        "FAMILY_INGEST", "IngestWorker", "IngestedCapture",
        "OUTCOME_INGESTED", "ROUTE_SURVEY", "ingest_capture",
        # catalog (B9): a capture attached BY RECORD, pixels absent
        "catalog_capture", "catalog_captures", "region_from_record",
        # records (R3); ``COLLECTION_CAPTURES`` left in B4. ``KIND_SCAN``/
        # ``scan_key``/``parse_scan_key`` are streaming ingestion's: the
        # DECLARED input an ingest attempt is named and spent by.
        "CaptureRecord", "FootingSpec",
        "KIND_ATTACHMENT", "KIND_CAPTURE", "KIND_REGION", "KIND_SCAN",
        "RECORD_FAMILIES",
        "REGION_KEY_PARTS", "RegionRecord", "attachment_key", "capture_key",
        "parse_region_key", "parse_scan_key", "region_key", "scan_key",
        # footing rasters (H4-LANES stage 1): the ladder's SUB-NATIVE
        # rungs, derived by the ingest fire and read by ``solve``. All
        # six cross — the plane opens rungs (``FootingRaster``,
        # ``footing_plan``, ``open_footing_raster``, ``footing_transform``,
        # ``footing_raster_for``) and ``prepared`` prepares in a
        # ``FootingFrame``, which is also the one place a coordinate
        # crosses between the native frame and a rung's. ``FootingPlan``
        # rides along as ``footing_plan``'s return type, which the plane
        # asks ``stands()`` of at the attachment gate.
        "FootingFrame", "FootingPlan", "FootingRaster", "footing_plan",
        "footing_raster_for", "footing_transform", "open_footing_raster",
        # no error taxonomy: ``LatticeNotFound`` is raised and handled
        # inside capture (B4).
    ),
    "holo2.solve": (
        # ``toys`` left in B4 and was deleted at H4 W1b (R11);
        # ``place_chain`` joined at H4 W2 with the family's second
        # descriptor route and was DELETED with the hint family by the
        # pull model's clean-slate sweep. ``calibration`` joined at H5 P1
        # (the CA2 region ctx reduce), bound module-qualified by the
        # composition root like the other two. ``refine`` joined at H5 P4
        # (RF1's certificate-labeled pose revision), the same way.
        "calibration", "payload", "placement", "refine",
        # the placement scheduler: family ``place`` as a
        # ``core.WorkSource``, bound by the composition root beside the
        # descriptor providers (H4 W2).
        "PlacementScheduler",
        # family ``ingest`` (H4 streaming ingestion): the declared scans
        # as descriptor work, bound by the same root. The frontier is
        # solve's because only the plane can resolve a declaration to an
        # acquisition; the
        # fire it mints is capture's.
        "RealIngestProvider",
        # the payload family's ledger reading: since tile family v4 the
        # observer derives the ATTEMPTED rank from it, so it crosses.
        "attempted_work_keys",
        # geometry the observer lays a window grid out with; solve's own
        # ``TILE_CELLS`` and ``CellLattice`` left in B4 (format publishes
        # the tile constant anybody reads).
        "WINDOW_CELLS", "WINDOW_STEP_CELLS", "window_starts",
        # ``TileState``/``tile_state`` moved here from ``records`` with
        # tile family v4: the four ranks are a DISPLAY view now.
        "DoneProjection", "StoreIndex", "TileMap", "TileState",
        "project_done", "tile_state",
        # the derived plane as the composition root opens it.
        # ``SessionPlane``/``CaptureView``/``capture_view``/``PlaneView``
        # and the ``plans`` vocabulary (``RegionView``, ``WindowPlan``,
        # ``region_view``, ``sample_support``, ``window_plans_for``) left
        # in B4: the engine relays the plane as ``core.SolveView`` and
        # never names solve's classes.
        "open_plane",
        # the volume close: since worklist B12 a TERMINAL CONSUMER the
        # composition root hands the engine, not a provider family.
        # ``certified_symbols`` is its interior and left in B4.
        "VolumeClose",
        # records (R3): most of §5 is written by a solve worker.
        # ``KIND_POOL``/``KIND_TILE``/``KIND_WINDOW`` left in B4 — the
        # kind strings that DO cross are the three below.
        # THE HINT VOCABULARY IS GONE ENTIRELY (the clean-slate sweep):
        # ``PoseHint``/``hint_key`` left at the W2 reshape, and
        # ``KIND_HINT`` — kept then because the e2e battery read it —
        # left with the family itself. The batteries that name it are
        # historical drivers in ``holo2/measure/``, outside the suite.
        "COLLECTION_CERTIFIED", "CalibrationRecord", "EvidenceObservation",
        "HeldoutGate", "KIND_CALIBRATION", "KIND_EVIDENCE",
        "KIND_POSE", "LabelPool",
        "MintRef", "PoseRecord", "TileRecord",
        "WindowRecord", "WindowStatus", "calibration_collection_key",
        "calibration_key",
        "evidence_collection_key", "evidence_key",
        "pack_observed_cells", "parse_evidence_key", "parse_tile_key",
        "parse_window_key", "pool_key", "pose_collection_key", "pose_key",
        # ``region_evidence_collection_key`` joined at the F2a review
        # (2026-08-23): ``holo2/tests/conftest.py`` names it to pin the
        # two collections a piece joins, which is the B4 rationale
        # (a name is public because something outside the package reads
        # it).
        "record_families", "region_evidence_collection_key",
        "region_pose_collection_key", "tile_key",
        "unpack_observed_cells", "window_key",
        # no error taxonomy: ``TileMapError`` is raised and handled
        # inside solve (B4).
    ),
    "holo2.engine": (
        # ``RecipeEntry`` builds a ``Recipe`` and only the recipe
        # crosses; ``PlaneFactory`` is ``open_session``'s own parameter
        # type; ``FireCountTripwire``/``NoProviderError`` are raised and
        # handled inside the engine. All four left in B4.
        "Orchestrator", "POLICY_ID",
        "Plane", "RECIPE_V1", "RECORD_FAMILIES", "Recipe",
        "RunOutcome", "SessionContext", "SessionIdentity",
        "open_session",
    ),
    "holo2.diag": ("StatusProvider", "finalize", "serve"),
}


@pytest.mark.parametrize("package", sorted(SURFACES))
def test_surface_is_pinned(package: str) -> None:
    module = importlib.import_module(package)
    assert sorted(module.__all__) == sorted(SURFACES[package]), (
        f"{package}.__all__ changed; update the pin deliberately")


@pytest.mark.parametrize("package", sorted(SURFACES))
def test_surface_names_resolve(package: str) -> None:
    module = importlib.import_module(package)
    missing = [name for name in module.__all__ if not hasattr(module, name)]
    assert not missing, f"{package} advertises absent names: {missing}"

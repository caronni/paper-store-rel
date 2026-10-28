"""core — the algorithm-free machine: facts, storage, commit, work protocol.

Imports stdlib + numpy ONLY (layering law, ``tests/test_layering.py``).
core knows no printed format, no pixels, and no solver: it stores facts
generically, binds attempt identities, arbitrates spend-once, and defines
the protocol a provider and a worker implement.

The names below are the whole public surface — other packages import them
from ``holo2.core``, never from a submodule (the pin lives in
``tests/test_surfaces.py``).

**RECORDS core owns** (R3). core owns the *mechanism* — ``ResourceKey``,
the typed ids, ``BlobRef``, and the ``RecordRegistry`` every other package
declares its families into — plus exactly two record families of its own:

* ``SubjectSpec`` (kind ``subject``) — a provider-minted work subject
  (M3); the work protocol's own fact, opaque to core beyond its family.
* ``CloseRecord`` (kind ``close``) — the session's terminality. Written by
  the close provider in ``solve``, but the law is core's: a terminal
  close freezes every later commit, and ``engine`` reads it for
  lifecycle. Neither core nor engine may import solve, so the record
  lives here; ``records.py`` states the reasoning in full.

Every other family belongs to the package that writes it —
``holo2.capture.RECORD_FAMILIES``, ``holo2.solve.record_families()``,
``holo2.engine.RECORD_FAMILIES`` — and the composition root builds one
registry from them (``core.compose``).

**Error taxonomy** (R1 cross-cutting adoption). core's exception types are
part of that surface, and cross-package code catches only these:
``CommitRefusal`` (with ``CertificateConflict`` and ``StateRegression``),
``ReplayError``, ``MalformedKeyError``, ``RegistryError`` and
``ProtocolViolation``. B4 pared the list to those with a cross-package
handler: ``BlobError``, ``CodecError``, ``DuplicateWrite``,
``SilentStage``, ``SpendConflict``, ``TerminalSessionError`` and
``UnknownRecordError`` are raised by core and caught inside core or by
core's own tests, so they are not declared here — the taxonomy law reads
DECLARED off ``__all__`` (``tests/test_error_taxonomy.py``), and one of
them joins this list in the same diff as the first cross-package
``except`` that names it. ``StoreError`` did exactly that at the C5
review fix (2026-08-22): the CLI reads a state's identity before owning
it, and turns the store's refusal into an exit line.
"""
from __future__ import annotations

from .blobs import StagedBlob, stage_array, stage_bytes
from .codec import canonical_json_bytes
from .commit import (CertificateConflict, CommitBatch, CommitEngine,
                     CommitRefusal, CommitResult, SpendProposal,
                     StateRegression, Subscription, Write, batch_id)
from .identity import SpendRecord
from .journal import (JOURNAL_NAME, ReplayCursor, ReplayError,
                      is_marker, marker_work_id)
from .keys import (AttemptIdentity, CaptureSha, FootingId,
                   KeyEmbed, KeyField, KeySpec, MalformedKeyError, PoolId,
                   Record, ResourceKey, StreamId, WorkId, WorkScope,
                   build_key, collection_key, key_parts, parse_key,
                   require_finite_positive, require_sha256_hex,
                   require_sorted_unique)
from .publish import publish_once
from .records import (CLOSE_KEY, KIND_SUBJECT, RECORD_FAMILIES,
                      BlobRef, CloseRecord, CloseStatus, SubjectSpec,
                      require_own_key)
from .registry import RecordFamily, RecordRegistry, RegistryError, compose
from .store import DEFAULT_SNAPSHOT_EVERY, Store, StoreError
from .trace import DEFAULT_TRACE_SAMPLE_EVERY, TraceWriter
from .view import SolveView
from .work import (Decline, ExpansionRequest, Lease, LeaseBook,
                   ProgressSink, ProtocolViolation, Provider, SourceJob,
                   WorkDescriptor, WorkResult, WorkSource, Worker,
                   check_progress, providers_by_family, providers_identity)

__all__ = [
    # B4 cut this list to what the tree consumes: a name no other package
    # imports is not core's surface, it is API kept alive by its own pin.
    # Everything dropped stays importable from its own core module and
    # rejoins this list in the diff that first imports it from another
    # package — ``digest_json``/``sha256_hex``, ``Lease``, ``SubjectId``,
    # ``KIND_CLOSE``/``KIND_COLLECTION``, ``subject_key``/
    # ``subject_collection_key``, and the seven exception types below.
    # codec / blobs
    "canonical_json_bytes",
    "StagedBlob", "stage_array", "stage_bytes",
    # commit
    "CommitBatch", "CommitEngine", "CommitResult", "SpendProposal",
    "Subscription", "Write", "batch_id",
    # identity. ``SpendRecord`` is the ledger's durable row: a derived
    # view that COUNTS spends (the payload family's CRC exposure) reads
    # it, and reading a row is not authority over the ledger.
    "SpendRecord",
    # typed ids (the ATOMS; a structured id IS its ResourceKey)
    "CaptureSha", "FootingId", "PoolId", "StreamId", "WorkId",
    # keys and the record vocabulary. ``KeySpec`` + its two slot types are
    # how a package DECLARES a kind's key instead of hand-spelling the
    # arity guard; the validators are the shared value checks a record's
    # ``__post_init__`` calls at the wall.
    "AttemptIdentity", "BlobRef", "CLOSE_KEY", "CloseRecord", "CloseStatus",
    "KIND_SUBJECT", "KeyEmbed", "KeyField",
    "KeySpec", "RECORD_FAMILIES",
    "Record", "RecordFamily", "RecordRegistry", "ResourceKey", "SubjectSpec",
    "build_key", "collection_key", "compose", "key_parts", "parse_key",
    "require_finite_positive", "require_own_key", "require_sha256_hex",
    "require_sorted_unique",
    # store / trace / publish, and the two cadence defaults the CLI and
    # the session both name (one owner each, on the surface both read).
    "DEFAULT_SNAPSHOT_EVERY", "DEFAULT_TRACE_SAMPLE_EVERY",
    "JOURNAL_NAME", "ReplayCursor", "Store", "is_marker",
    "marker_work_id",
    "TraceWriter", "publish_once",
    # the work protocol. ``SourceJob``/``WorkSource`` are H4 W2's second
    # admission shape (the pull model): solve implements one, the engine
    # admits it beside the descriptor queue, so the pair crosses two
    # package boundaries and belongs on this surface.
    # ``Lease`` joined the surface at W4: a solve-side worker declares the
    # residency its fire holds (the cold pair's page transforms) and the
    # orchestrator's book takes it, so the type crosses the same boundary
    # the book already did.
    "Decline", "ExpansionRequest", "Lease", "LeaseBook",
    "ProgressSink", "Provider", "SolveView", "SourceJob", "WorkDescriptor",
    "WorkResult", "WorkScope", "WorkSource", "Worker", "check_progress",
    "providers_by_family", "providers_identity",
    # error taxonomy: the types another package actually catches.
    # ``StoreError`` JOINED at the C5 review fix (2026-08-22), under the
    # rule stated in the module docstring: ``cli.py`` reads a state
    # directory's identity before it owns it, so a state this build may
    # not open now refuses during ARGUMENT CHECKING — where the file's
    # whole discipline is that an operator meets a ``confetti2:`` line
    # and not a traceback. That ``except`` is the first cross-package
    # handler naming the type, so this is the diff it joins in.
    "CertificateConflict", "CommitRefusal", "MalformedKeyError",
    "ProtocolViolation", "RegistryError", "ReplayError", "StateRegression",
    "StoreError",
]

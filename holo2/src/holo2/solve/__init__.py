"""solve — placement, payload and projection: the algorithms.

Imports: ``core``, ``format``, ``capture``. solve turns pixels plus format
truth into proposals: cell/pixel geometry, the word-grid placer, the
photometric calibration fits, the per-tile certification chain, the
tile-map projection that says what is already done, and the providers
that expand all of it into schedulable work (``PROVIDERS.md``).

R1 shape: the worker input is the ``PlaneView`` protocol declared here
(``core.SolveView`` plus format row, regions, footings, window plans and
rasters), so nothing in ``solve`` names an engine type.

R2 gave that protocol a home-grown implementation: ``SessionPlane`` is
the derived world a session schedules over — captures, regions on their
lattices, window plans, tile map, done projection — which used to live in
``engine/runtime.py`` and could not stay there, since every type on it is
a format, capture or solve type. The engine owns commit, lineage and
lifecycle; it relays this object to workers as ``core.SolveView``. With
the last cycle gone, the worker families are on this surface like
everything else; ``real_workers`` split along its own seam into
``placement`` (the word kernel; H4 W1 replaced the ``placement_h3bis``
stand-in with the real E022 route, and H4 W2's pull model dissolved its
provider into ``place_sched`` + ``place_job``) and ``payload``
(frozen evidence -> certificates). The binding that names them is the
composition root's (``cli.real_providers`` for the descriptor families,
``cli.real_source`` for the placement scheduler, which is a
``core.WorkSource`` rather than a provider). The volume close
is NOT one of them: since worklist B12 it is the engine's terminal
consumer (``VolumeClose``), handed over separately by the same root.

**RECORDS solve owns** (R3, ``records.py``): every fact a solve worker
mints, which is most of §5.

* ``TileRecord`` (kind ``tile``, **v4**) with ``MintRef`` — the logical
  authority. Its law (certified content never changes, the footing sets
  only grow) is registered WITH the family, so the commit layer applies
  it without knowing what a certificate is. The four-rank vocabulary
  ``TileState`` is a DISPLAY view and lives in ``tilemap``.
* ``PoseRecord`` (kind ``pose``, **v4** — canonical affine terms) and
  ``WindowRecord`` (kind ``window``, **v5** — an OUTCOME only: placed-by,
  or retired with a reason) — the physical plane's committed geometry.
* ``EvidenceObservation`` (kind ``evidence``, **v3**) — the durable
  payload atom.
* ``LabelPool`` (kind ``pool``, v1) and ``CalibrationRecord`` (kind
  ``calibration``, **v2**) — the calibration reduce's scope and fits.

The v-bumps at ``pose``/``window``/``evidence``/``calibration`` are the
hash-free identity law (2026-08-11): a record's key IS its defining
values, so the id fields are gone and ``window_key``/``pose_key``/
``calibration_key`` build a key from the values themselves. ``tile`` v3
and ``window`` v3 finish it (2026-08-12): ``MintRef.attempt_digest`` and
``WindowRecord.routes_spent``/``RouteSpend`` are deleted — a digest of an
identity the key already carries, and a spend projection the durable
ledger already owns and no layer ever wrote. ``window`` **v5** is H4 W2's
own (ruling Q2): the two scheduling statuses shed with the pull model, so
what stays durable about a window is what BECAME of it.

solve publishes ``record_families(page_domain)`` rather than a plain
tuple: the pose family's structural validator is bound to the session's
declared page domain (§5.1) at composition time.

**Error taxonomy** (R1): ``TileMapError`` is solve's only exception, and
since B4 it is not on the surface — nothing outside solve raises or
catches it, and a declared type with no cross-package handler is API kept
alive by its own pin. Cross-package code here catches core's, nothing
else.
"""
from __future__ import annotations

from . import calibration, payload, placement, refine
from .ingest import RealIngestProvider
from .payload import attempted_work_keys
from .place_sched import PlacementScheduler
from .close import VolumeClose
from .geometry import WINDOW_CELLS, WINDOW_STEP_CELLS, window_starts
from .families import record_families
from .plane import open_plane
from .records import (COLLECTION_CERTIFIED, CalibrationRecord,
                      EvidenceObservation, HeldoutGate, KIND_CALIBRATION,
                      KIND_EVIDENCE, KIND_POSE, LabelPool, MintRef,
                      PoseRecord, TileRecord,
                      WindowRecord, WindowStatus, calibration_collection_key,
                      calibration_key,
                      evidence_collection_key, evidence_key,
                      pack_observed_cells, parse_evidence_key, parse_tile_key,
                      parse_window_key, pool_key, pose_collection_key,
                      pose_key, region_evidence_collection_key,
                      region_pose_collection_key,
                      tile_key, unpack_observed_cells, window_key)
from .tilemap import (DoneProjection, StoreIndex, TileMap, TileState,
                      project_done, tile_state)

__all__ = [
    # B4 cut this list to what the tree consumes. The two worker families
    # stay because the composition root binds them module-qualified;
    # ``toys`` left in B4 as "not production surface" and was DELETED
    # wholesale at H4 W1b (H4-PLAN R11). So did the
    # interior types of solve's own derivation, each still importable
    # from its module and each rejoining this list in the diff that first
    # imports it from another package: ``SessionPlane``/``CaptureView``/
    # ``capture_view`` (the engine relays the plane as ``core.SolveView``
    # and never names its class), ``PlaneView`` (the worker input, typed
    # against inside solve), ``RegionView``/``WindowPlan``/``region_view``/
    # ``sample_support``/``window_plans_for`` (the plane builds them),
    # ``CellLattice``, solve's ``TILE_CELLS`` (format publishes the one
    # anybody reads), ``certified_symbols`` (``VolumeClose`` is what
    # crosses), the three unread ``KIND_*`` strings, and ``TileMapError``
    # (raised and handled inside solve, so not a declared cross-package
    # catch — see ``tests/test_error_taxonomy.py``).
    # the three descriptor families the composition root binds
    # module-qualified: calibration joined at H5 P1 (the CA2 region ctx
    # reduce, ``calibration.CtxCalibrationProvider``) and refine at H5 P4
    # (RF1's certificate-labeled pose revision,
    # ``refine.PoseRefineProvider``).
    "calibration", "payload", "placement", "refine",
    # the placement scheduler: family ``place`` as a ``core.WorkSource``
    # (H4 W2's pull model), bound by the composition root beside the
    # descriptor providers
    "PlacementScheduler",
    # family ``ingest`` (H4 streaming ingestion): the declared scans as
    # descriptor work, bound by the same root. The FIRE it mints is
    # ``capture``'s
    # (``IngestWorker``); what lives here is the frontier, because only
    # the plane can say which declaration is which acquisition.
    "RealIngestProvider",
    # the payload family's ledger reading, which the observer
    # derives the ATTEMPTED rank from (tile family v4)
    "attempted_work_keys",
    # geometry the observer lays a window grid out with
    "WINDOW_CELLS", "WINDOW_STEP_CELLS", "window_starts",
    # tile-map projection
    "DoneProjection", "StoreIndex", "TileMap", "TileState",
    "project_done", "tile_state",
    # the derived plane, as the composition root opens it
    "open_plane",
    # the volume close: a terminal consumer, not a provider (B12)
    "VolumeClose",
    # records (R3). The hint vocabulary left this surface entirely with
    # the family (H4 W2's clean-slate sweep): there is no hint kind to
    # export, and the batteries that read one are historical drivers.
    "COLLECTION_CERTIFIED", "CalibrationRecord", "EvidenceObservation",
    "HeldoutGate", "KIND_CALIBRATION", "KIND_EVIDENCE",
    "KIND_POSE", "LabelPool",
    "MintRef", "PoseRecord", "TileRecord",
    "WindowRecord", "WindowStatus", "calibration_collection_key",
    "calibration_key",
    "evidence_collection_key", "evidence_key",
    "pack_observed_cells", "parse_evidence_key", "parse_tile_key",
    "parse_window_key", "pool_key", "pose_collection_key", "pose_key",
    "record_families", "region_evidence_collection_key",
    "region_pose_collection_key", "tile_key",
    "unpack_observed_cells", "window_key",
]

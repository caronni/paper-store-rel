"""CA2 goes live: the region ctx calibration family (H5 P1).

The pull-model translation of the census's CA2 row (PROVIDERS §3): a
calibration PROVIDER mints one spendable fit-descriptor per
(footing, region, label-pool member-set version), and the fit fire calls
the CARRIED ``detect`` arithmetic unchanged — ``fit_context`` is held-out
gated adopt-or-refuse INSIDE the fit, so there is no chain of workers and
no arm scheduling. A refused fit leaves the marginal path untouched and
commits its refusal reason.

WHAT THE FIT READS (the prospective-only law). Label sites come from
format-known cells of COMMITTED placements only: the pool's members are
the committed, non-quarantined poses of one (footing, region) —
:func:`pool_members` asks ``quarantine.is_quarantined``, the third reader
of the one predicate — and each member's label population is derived at
fire time from its own evidence pieces plus the reference field, exactly
as v1's ``_payload_context.apply_region_context`` derives it from each
accepted window:

* the piece's stored LLRs ARE the calibrated marginal (``place_shared``
  writes ``calibration.llr(scores)``), so ``baseline_llr`` is a blob
  read, not a re-derivation;
* provisional ink is ``marginal > 0`` and the neighbour counts run over
  the pose's own observed cells in ABSOLUTE page coordinates
  (``detect.context_neighbour_counts``), so cells split across tiles
  reconstruct their eight-neighbourhoods exactly as the window-shaped
  v1 computation had them;
* labels are the reference field's printed values at its known sites,
  split by v1's own site parity ``(131*y + 17*x) & 1`` into SEARCH and
  VALIDATION. Which field that is, is P2's whole subject: the cold-legal
  format field (``reference.V1ReferenceField`` — word and filler cells)
  ENRICHED with the committed certificate frontier, where every cell of a
  certified tile is a trustworthy label
  (``certified_labels.CertifiedLabelSource``). The split is deliberately
  NOT re-cut for the enriched sites: ``(131*y + 17*x) & 1`` is the
  carried ctx arithmetic, and v1's block-wise holdout belongs to the
  POSE fit (``certified_refine._block_validation``), which is a different
  fit with its own weights;
* physical site ids are the page-cell coordinates themselves, shared
  across members, so duplicate observations of one physical label weigh
  ONE in the pooled fit (``ContextObservations.weights``, v1's
  ``_physical_cell_ids`` semantics under an injective relabeling).

WHAT THE FIT WRITES. One :class:`~holo2.solve.records.LabelPool` per
(footing, region) — grow-only, per its F-08 transition — and one
:class:`~holo2.solve.records.CalibrationRecord` per fit, adopted or
refused, whose params blob carries the nine offsets plus the fit's own
support counts and losses. The record's identity is (scope, algorithm,
params content address), so an identical refit is an idempotent no-op and
a differing one is a NEW record at a new key; ADOPTED pool fits join the
pool's calibration collection (``records._calibration_collections``),
which is the one region-scoped key a payload decode subscribes to and it
versions on ADOPTION only.

WHERE THE CORRECTION APPLIES (the load-bearing design sentence, H5-PLAN).
Evidence keeps its calibrated MARGINAL LLRs forever; the correction
applies at DECODE ASSEMBLY (:func:`apply_component_context`, called by
``payload.RealPayloadWorker``): bins are derived from the assembled
component's own observed cells and provisional ink, the offsets are the
adopted fit's, and the kernel is the carried
``detect.apply_context_offsets`` — frozen clamps, bin −1 untouched. A
cell on the component's tile boundary has an incomplete neighbourhood
inside the 64-cell tile the fire may see (subscription scoping forbids
sibling evidence), so it is bin −1 and keeps its marginal — the
conservative reading of the one place tile-scoped assembly differs from
v1's window-scoped apply. With no adopted fit the component is returned
UNTOUCHED — the same object, so the refused path is bit-for-bit the
pre-H5 path.

WHICH FIT IS CURRENT (:func:`adopted_context_offsets`). Records are
frozen and never retired, so a refit that adopts different offsets leaves
two adopted records standing. The reader picks the one fitted over the
LARGEST search population (read off the params blob), ties broken on the
params content address — deterministic on any store state, independent of
commit arrival order, and rebuildable, which a latest-write rule is not.

RE-WORK AGING is not implemented here and must not be: the fit descriptor
spends at the wall exactly as payload's do, so ``engine.recipe.work_price``
lifts every re-fit into the re-work band by construction (first fit at
the recipe's 15, refits at 90+), and a region refit follows a BATCH of
new labels rather than each one. P2 leans on this hard: the enrichment's
re-arm is ``COLLECTION_CERTIFIED``, which is GLOBAL — every certificate
anywhere moves it, so every region's fit re-arms on every certified tile
— and it is the re-work band, not a finer subscription, that turns that
into one refit per batch. A region-scoped certified collection would be a
NEW durable membership mechanism; the aging that already exists is the
cheaper answer, and the coarseness costs only descriptor arming.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from ..capture import KIND_REGION
from ..core import (AttemptIdentity, ExpansionRequest, FootingId, PoolId,
                    ProgressSink, ResourceKey, SolveView, StagedBlob,
                    WorkDescriptor, WorkResult, Write, stage_array)
from ..format import TILE_CELLS, FormatRowSpec, TileFormat, tile_format_for
from . import detect
from .certified_labels import (LABEL_KIND_CERTIFIED, CertifiedLabelSource,
                               FormatOnlyLabels)
from .generation import live_generation
from .keys import (COLLECTION_CERTIFIED, EVIDENCE_KEY_PARTS, KIND_EVIDENCE,
                   KIND_POSE, KIND_WINDOW, POSE_KEY_PARTS, WINDOW_KEY_PARTS,
                   calibration_key, parse_window_key, pool_key,
                   region_evidence_collection_key,
                   region_pose_collection_key)
from .place_tiers import LANE_COST_PER_RUNG
from .quarantine import is_quarantined
from .records import (CalibrationRecord, EvidenceObservation, HeldoutGate,
                      LabelPool, unpack_observed_cells)
from .reference import ReferenceFieldProvider, V1ReferenceField
from .view import PlaneView, as_plane

FAMILY_CALIBRATION = "calibration"

#: The carried arm's name, spelled once for the algorithm field, the
#: route and the census row (PROVIDERS CA2: pool / ``ctx-pava-v1`` /
#: footing).
CTX_ALGORITHM = "ctx-pava-v1"
ROUTE_CTX = CTX_ALGORITHM

#: Spend outcomes. ``adopted`` is ``detect``'s own acceptance; every
#: refusal carries the fit's reason so the ledger's per-outcome counts
#: say WHY a pool refused, not merely that it did.
OUTCOME_ADOPTED = "adopted"
OUTCOME_REFUSED_PREFIX = "refused_"

#: The params blob layout: nine offsets, then the fit's own accounting.
#: The offsets are what apply reads; the support counts are what the
#: current-fit ranking reads; the losses and the flag make two fits that
#: differ in ANYTHING differ in content — which is what keeps the
#: content-addressed identity honest for refusals too (zeros offsets with
#: different floors are different records, and an identical re-derivation
#: is the same one).
CTX_BINS = detect.N_CONTEXT_BINS
PARAM_LENGTH = CTX_BINS + 7
_ABSENT_LOSS = -1.0

#: F1 (ruling J2-1, 2026-08-23) appends the PER-WINDOW HELD-OUT LOSSES to
#: the same blob: ``[member count][digest, loss] * count``. That is the
#: statistic v1's ownership freeze ranks candidate windows by
#: (``receive/payload.py:138-140``), and the ctx fit is the one fire that
#: can compute it — v1's key is the loss the ctx arm OVERWRITES
#: (``_payload_context.py:284-295``), over the WINDOW's own held-out
#: format-known sites. Ranking on the marginal loss instead is a
#: different and measurably weaker rule (22/30 against 26/30 on the e029
#: gap tiles, ``detect/DETECTION-GAP-VERIFY.md`` correction 1).
#:
#: Why the blob and not a record field: a params array is bulk the record
#: already names by content address, and its LENGTH is self-describing —
#: a pre-F1 blob is exactly ``PARAM_LENGTH`` long and reads back as "no
#: published losses". No family version moves, so the archived states F1
#: is measured on stay open. See ``records``' halo comment for the same
#: choice on the other half.
_MEMBER_STRIDE = 2
#: 52 bits of the member pose key's SHA-256 — an integer float64 holds
#: exactly, so the blob stays one float array. Collisions are refused at
#: write time rather than tolerated (:func:`_member_loss_params`).
_DIGEST_HEX = 13


# ------------------------------------------------------------ identities

def ctx_pool_id(footing_id: FootingId, region: ResourceKey) -> PoolId:
    """The region ctx pool's id: ``ctx|<footing>|<region parts>``.

    The pool key's one slot is a single string (``keys.pool_key``), so
    the defining values are joined here — with an injectivity argument
    rather than an escape: a footing id is ``<hex>:<num>/<den>``
    (``core.keys.FootingId``) and region parts are a 64-digit hex digest
    and five decimal integers (``capture.REGION_SPEC``), so ``|`` occurs
    in no component and the join is invertible by inspection. Should the
    pool family ever grow a second scope shape, the structured-key form
    (rule 2 of ``core.keys``) is the upgrade path.
    """
    if region.kind != KIND_REGION:
        raise ValueError(f"not a region key: {region}")
    return PoolId("|".join(("ctx", str(footing_id), *region.parts)))


def ctx_pool_key(footing_id: FootingId, region: ResourceKey) -> ResourceKey:
    """The pool key of one (footing, region)'s region ctx label pool."""
    return pool_key(ctx_pool_id(footing_id, region))


def pose_pool_scope(pose_id: ResourceKey
                    ) -> tuple[FootingId, ResourceKey] | None:
    """The (footing, region) a pose key names — pure key arithmetic.

    ``None`` for anything that is not a well-formed pose key (a test
    double's string id, say): a piece whose provenance is not a real pose
    belongs to no pool and takes no correction.
    """
    if (not isinstance(pose_id, ResourceKey) or pose_id.kind != KIND_POSE
            or len(pose_id.parts) != POSE_KEY_PARTS):
        return None
    window = ResourceKey(KIND_WINDOW, pose_id.parts[:WINDOW_KEY_PARTS])
    footing_id, region, _extent = parse_window_key(window)
    return footing_id, region


def pool_of_evidence(key: ResourceKey) -> ResourceKey | None:
    """The ctx pool one evidence piece's labels would feed — or ``None``.

    Read off the key alone (§5.4 embeds the pose, the pose embeds the
    window, the window carries footing and region), so a payload worker
    can name its region-scoped subscription without touching a record.
    """
    if key.kind != KIND_EVIDENCE or len(key.parts) != EVIDENCE_KEY_PARTS:
        return None
    pose = ResourceKey(KIND_POSE,
                       key.parts[EVIDENCE_KEY_PARTS - POSE_KEY_PARTS:])
    scope = pose_pool_scope(pose)
    if scope is None:
        return None
    return ctx_pool_key(*scope)


# ----------------------------------------------------- the pool frontier

def pool_scopes(plane: PlaneView) -> tuple[tuple[FootingId, ResourceKey],
                                           ...]:
    """Every (footing, region) with a committed, NON-QUARANTINED pose.

    Not "live pose" (W3 review, 2026-08-23): since W3 that is a term of
    art for ``StoreIndex.live_pose``, the latest committed pose of an
    extent, and the filter here is ``is_quarantined``. This family
    deliberately does NOT narrow to live poses — the pool is
    evidence-scoped and affine-blind, and the reasoning is in
    ``solve/DESIGN.md``.

    Eligibility is expansion: a pool with no member mints no descriptor,
    so the family's first fire happens after the first placement commits
    — at which point one window's format-known cells usually already
    clear the carried floors.
    """
    scopes: set[tuple[FootingId, ResourceKey]] = set()
    for pose_id, pose in plane.index().poses.items():
        if is_quarantined(pose):
            continue
        scope = pose_pool_scope(pose_id)
        if scope is not None:
            scopes.add(scope)
    return tuple(sorted(scopes))


def pool_members(plane: PlaneView, footing_id: FootingId,
                 region: ResourceKey) -> tuple[ResourceKey, ...]:
    """The committed, NON-QUARANTINED poses of one (footing, region).

    The prospective-only law with the quarantine filter applied AT POOL
    ASSEMBLY: ``is_quarantined`` is the third reader of the one predicate
    (consult and payload read-set are the other two), so labels from
    condemned material never enter a pool. Sorted — the members enter the
    fit's read-set, and a read-set's order is part of its identity (§7).
    """
    members: list[ResourceKey] = []
    for pose_id, pose in plane.index().poses.items():
        if is_quarantined(pose):
            continue
        scope = pose_pool_scope(pose_id)
        if scope is not None and scope == (footing_id, region):
            members.append(pose_id)
    return tuple(sorted(members))


# ----------------------------------------------------- the label harvest

@dataclass(frozen=True)
class _Population:
    """One side of the pooled region split, as ``detect`` wants it."""

    llr: np.ndarray
    counts: np.ndarray
    labels: np.ndarray
    site_ids: np.ndarray

    @property
    def unique_class_support(self) -> tuple[int, int]:
        _, first = np.unique(self.site_ids, return_index=True)
        labels = self.labels[first]
        ones = int(labels.sum())
        return int(labels.size - ones), ones


def _pieces_by_pose(plane: PlaneView, footing_id: FootingId,
                    members: frozenset[ResourceKey]
                    ) -> dict[ResourceKey, list[ResourceKey]]:
    """One pass over the evidence index: each member's piece keys, sorted.

    A pose does not index its pieces (the arrow runs the other way by
    §5.4), so this is the same one-pass grouping ``quarantine`` pays on a
    contradiction — paid here once per fit fire, which is a reduce.

    **THE LIVE GENERATION IS TAKEN HERE** (F2a, ruling J2-3,
    2026-08-23), which is the pool's half of the payload read-set's rule:
    once the re-sample has emitted at a window's revised pose, that
    window contributes its LIVE pieces only. Without it one physical
    label site would enter the pooled fit twice — once at the parent's
    marginal and once at the revision's — at half weight each, which is
    a fit over a population that exists nowhere. It is the IDENTITY on
    every state written before F2a (:mod:`holo2.solve.generation`), and
    it is applied to the whole footing's harvest rather than per tile
    because a pool's population is per WINDOW.
    """
    live = plane.index().live_poses
    grouped: dict[ResourceKey, list[ResourceKey]] = {}
    for key in live_generation(live, [
            key for key, footing in plane.index().evidence_footings.items()
            if footing == footing_id]):
        pose = ResourceKey(KIND_POSE,
                           key.parts[EVIDENCE_KEY_PARTS - POSE_KEY_PARTS:])
        if pose in members:
            grouped.setdefault(pose, []).append(key)
    return {pose: sorted(keys) for pose, keys in grouped.items()}


def _member_cells(plane: PlaneView, piece_keys: Iterable[ResourceKey]
                  ) -> tuple[np.ndarray, np.ndarray]:
    """One member's observed cells (absolute page yx) and marginal LLRs.

    Pieces are per (tile, pose) and tiles are disjoint, so the union has
    no duplicate cells — which ``detect.context_neighbour_counts``
    requires and would refuse.
    """
    cells: list[np.ndarray] = []
    marginal: list[np.ndarray] = []
    for key in piece_keys:
        observation = plane.record(key)
        if not isinstance(observation, EvidenceObservation):
            continue
        llr = np.asarray(plane.read_array(observation.llr_ref),
                         np.float64).reshape(TILE_CELLS, TILE_CELLS)
        observed = unpack_observed_cells(
            plane.read_array(observation.observed_ref),
            (TILE_CELLS, TILE_CELLS))
        ys, xs = np.nonzero(observed)
        cells.append(np.stack(
            (ys + observation.ty * TILE_CELLS,
             xs + observation.tx * TILE_CELLS), axis=1).astype(np.int64))
        marginal.append(llr[observed])
    if not cells:
        empty = np.zeros((0, 2), np.int64)
        return empty, np.zeros(0, np.float64)
    return np.concatenate(cells), np.concatenate(marginal)


@dataclass(frozen=True)
class _MemberHeldout:
    """One member window's HELD-OUT format-known sites, as v1 ranks them.

    v1's key is a per-WINDOW quantity computed over
    ``((131*y + 17*x) & 1) & (reference_values >= 0)`` — the window's own
    held-out known sites, with NO validity filter and NO site-id dedup
    (``_payload_context.py:288-294``; the dedup weights belong to the
    POOLED fit, not to this loss). Cells whose eight-neighbourhood is
    incomplete are in it at bin -1, uncorrected, exactly as v1 leaves
    them.
    """

    pose_id: ResourceKey
    marginal: np.ndarray
    bins: np.ndarray
    labels: np.ndarray


def binary_logloss(llr: np.ndarray, labels: np.ndarray) -> float:
    """v1's ``_payload_context._binary_logloss``, unweighted.

    ``logaddexp(0, x) - y*x`` on log-odds — the same function
    ``detect._logloss`` computes from the other side, spelled here the
    way the site F1 reproduces spells it.
    """
    x = np.asarray(llr, np.float64)
    y = np.asarray(labels, np.float64)
    return float(np.mean(np.logaddexp(0.0, x) - y * x))


def region_populations(plane: PlaneView, reference: ReferenceFieldProvider,
                       footing_id: FootingId,
                       members: tuple[ResourceKey, ...],
                       progress: ProgressSink | None = None
                       ) -> tuple[_Population, _Population]:
    """The pooled SEARCH/VALIDATION context populations of one pool."""
    search, validation, _members = region_fit_inputs(
        plane, reference, footing_id, members, progress)
    return search, validation


def region_fit_inputs(plane: PlaneView, reference: ReferenceFieldProvider,
                      footing_id: FootingId,
                      members: tuple[ResourceKey, ...],
                      progress: ProgressSink | None = None
                      ) -> tuple[_Population, _Population,
                                 tuple[_MemberHeldout, ...]]:
    """The pooled populations AND each member's held-out sites (F1).

    v1's per-window harvest (``_payload_context.apply_region_context``),
    with the window's arrays reconstructed from the member's own pieces:
    marginal from the stored LLRs, provisional ink ``marginal > 0``,
    neighbour counts over the member's absolute page cells, labels from
    the reference field at format-known sites, the ``(131*y + 17*x) & 1``
    site parity, and page-cell site ids shared across members so one
    physical label weighs one however many members observed it.

    The third return value is F1's addition and is the SAME PASS: v1
    ranks freeze candidates by each window's held-out loss AFTER the
    region's offsets are applied to that window, so the loss has to be
    computed where the whole window is in hand — here — and only the
    held-out subset is kept, which is a few percent of the cells.
    """
    spec = reference.spec
    height, width = spec.cells_yx
    index = plane.index()
    grouped = _pieces_by_pose(plane, footing_id, frozenset(members))
    sides: dict[bool, list[tuple[np.ndarray, np.ndarray, np.ndarray,
                                 np.ndarray]]] = {False: [], True: []}
    heldouts: list[_MemberHeldout] = []
    for pose_id in members:
        pose = index.poses.get(pose_id)
        keys = grouped.get(pose_id, ())
        if pose is None or not keys:
            continue
        cells, marginal = _member_cells(plane, keys)
        if not cells.size:
            continue
        counts, valid = detect.context_neighbour_counts(
            cells, marginal > 0.0)
        page = reference.page(pose.page)
        known = page.sites[cells[:, 0], cells[:, 1]]
        expected = page.values[cells[:, 0], cells[:, 1]]
        heldout = (((131 * cells[:, 0] + 17 * cells[:, 1]) & 1) == 1)
        ids = ((np.int64(pose.page) * height + cells[:, 0]) * width
               + cells[:, 1])
        for side in (False, True):
            select = known & valid & (heldout if side else ~heldout)
            if select.any():
                sides[side].append((marginal[select], counts[select],
                                    expected[select], ids[select]))
        rank = known & heldout
        if rank.any():
            heldouts.append(_MemberHeldout(
                pose_id, marginal[rank],
                detect.context_bins(counts, valid=valid)[rank],
                np.asarray(expected, bool)[rank]))
        if progress is not None:
            progress.emit(1, "member-harvested")

    def pooled(parts: list[tuple[np.ndarray, np.ndarray, np.ndarray,
                                 np.ndarray]]) -> _Population:
        if not parts:
            return _Population(np.zeros(0, np.float64), np.zeros(0, np.int8),
                               np.zeros(0, bool), np.zeros(0, np.int64))
        return _Population(
            np.concatenate([row[0] for row in parts]),
            np.concatenate([row[1] for row in parts]).astype(np.int8),
            np.concatenate([row[2] for row in parts]).astype(bool),
            np.concatenate([row[3] for row in parts]))

    return pooled(sides[False]), pooled(sides[True]), tuple(heldouts)


def member_digest(pose_id: ResourceKey) -> float:
    """The 52-bit key the params blob names a member window by.

    Content-derived, total and rebuildable — the properties the blob
    needs, since a member set grows and an index into it would not
    survive the next fit. Exactly representable in float64, which is what
    lets the losses ride the params array instead of a record field.
    """
    return float(int(
        hashlib.sha256(str(pose_id).encode("utf-8")).hexdigest()[:_DIGEST_HEX],
        16))


def member_window_losses(members: Iterable[_MemberHeldout],
                         offsets: np.ndarray | None) -> dict[ResourceKey,
                                                             float]:
    """Each member window's held-out loss, as v1's freeze ranks them.

    With ``offsets`` (the region ADOPTED), the loss is measured on the
    CORRECTED window — v1 overwrites ``heldout_logloss`` with exactly
    this number on adoption (``_payload_context.py:290-294``). With
    ``None`` (refused, or not eligible) the marginal loss stands, which
    is the number v1's CA1 left on the window
    (``_payload_sampling._calibrate:384-388``, the same quantity spelled
    from probabilities).
    """
    out: dict[ResourceKey, float] = {}
    for member in members:
        llr = (member.marginal if offsets is None
               else detect.apply_context_offsets(
                   member.marginal, member.bins, offsets))
        out[member.pose_id] = binary_logloss(llr, member.labels)
    return out


def _member_loss_params(losses: dict[ResourceKey, float]) -> np.ndarray:
    """The losses' half of the params blob: count, then digest/loss pairs.

    Sorted by pose key so the blob — and therefore the record's content
    address — is a function of the fit and not of dict order. A digest
    collision is REFUSED rather than tolerated: two windows sharing a key
    would silently hand one window's calibration quality to the other.
    """
    items = sorted(losses.items())
    digests = [member_digest(pose_id) for pose_id, _loss in items]
    if len(set(digests)) != len(digests):
        raise ValueError(
            "calibration: member digest collision in a ctx fit's window "
            "losses — two poses share 52 bits of SHA-256")
    body = np.empty(_MEMBER_STRIDE * len(items), np.float64)
    body[0::_MEMBER_STRIDE] = digests
    body[1::_MEMBER_STRIDE] = [loss for _pose_id, loss in items]
    return np.concatenate((np.asarray([float(len(items))]), body))


def published_losses(params: np.ndarray) -> dict[float, float]:
    """The digest -> window-loss map a params blob carries, if any.

    A pre-F1 blob is exactly ``PARAM_LENGTH`` long and answers ``{}`` —
    such a pool publishes no ranking statistic and its poses fall back to
    the pose-key order, which is what holo2 did before F1.
    """
    if params.size <= PARAM_LENGTH:
        return {}
    count = int(params[PARAM_LENGTH])
    body = params[PARAM_LENGTH + 1:]
    if count < 0 or body.size != _MEMBER_STRIDE * count:
        raise ValueError(
            "calibration: malformed ctx params blob — "
            f"{body.size} trailing values for {count} members")
    return dict(zip(body[0::_MEMBER_STRIDE].tolist(),
                    body[1::_MEMBER_STRIDE].tolist()))


def _floor_reason(search: _Population, validation: _Population) -> str:
    """v1's partial-population cascade (``_partial_context_decision``),
    for the case one pooled side is empty — where ``ContextObservations``
    cannot even be constructed. A two-sided population takes the carried
    ``fit_context`` path instead, whose own floors state the same
    cascade."""
    s0, s1 = search.unique_class_support
    v0, v1 = validation.unique_class_support
    if s0 + s1 < detect.CTX_MIN_SEARCH:
        return "insufficient_search_support"
    if min(s0, s1) < detect.CTX_MIN_SEARCH_PER_CLASS:
        return "search_class_starved"
    if v0 + v1 < detect.CTX_MIN_VALIDATION:
        return "insufficient_validation_support"
    return "validation_class_starved"


# ------------------------------------------------------------ the worker

class CtxFitWorker:
    """ONE region ctx fit: harvest, carried fit, adopt-or-refuse, commit."""

    task_class = FAMILY_CALIBRATION

    def __init__(self, pool: ResourceKey, footing_id: FootingId,
                 region: ResourceKey,
                 labels: CertifiedLabelSource | FormatOnlyLabels) -> None:
        self.pool = pool
        self.footing_id = footing_id
        self.region = region
        self._labels = labels

    @property
    def route(self) -> str:
        return ROUTE_CTX

    def read_keys(self, view: SolveView) -> tuple[ResourceKey, ...]:
        """The pool, its membership resource, and the members themselves.

        * the POOL key — the record this fit grows;
        * the (footing, region) pose COLLECTION — how a NEW member's
          arrival re-arms the fit (a pose key cannot be named before the
          pose exists);
        * the (footing, region) EVIDENCE collection — how a member that
          gains PIECES without being a new pose re-arms it (F2a review
          fix, 2026-08-23). C4 §3.3(5) is v1's rule and this is what
          implements it: after ``_payload_reuse.sample_refined_reusing_
          generation`` re-samples, *"the region-coupled ctx arm re-runs
          over that full population"*. The re-read commits pieces at a
          live pose and deliberately no pose record, so without this key
          nothing the fit reads moves and the fit that stands forever is
          the one fitted when the REVISION committed — i.e. over the
          parent's pieces, before the revision owned any. MEASURED
          before the fix: 0 of 4 pools on either real sheet had a fit
          that had seen a re-read's pieces; 0 of 255 Xerox re-read poses
          had a published window loss, so F1's ownership key fell back
          to pose-id order on exactly the windows the re-read makes
          decode-authoritative. It buys no wake on the ordinary path:
          an emission commits pose and pieces together
          (:func:`holo2.solve.keys.region_evidence_collection_key`);
        * the member POSE keys — how a quarantine mid-flight kills the
          fit at the wall's existing staleness check (the condemnation
          bumps the pose, and the pieces move in the same batch, so the
          pose versions bind the whole label input);
        * ``COLLECTION_CERTIFIED`` (H5 P2) — how the ENRICHED half of the
          label population re-arms, and ONLY when the source enriches: a
          format-only fit's labels cannot move with a certificate, so
          subscribing it would buy one wasted spend per certificate
          batch. A certificate is a label site, so a new one is new
          label material by exactly the same argument a new pose is, and
          the tile family already declares this collection
          (``families._tile_collections``): no new wake kind, no new
          durable state. It is global rather than region-scoped on
          purpose — see the module docstring's re-work paragraph.

        Deliberately NOT the adoption collection: the fit never reads a
        prior fit, and naming a key its own commit bumps would buy one
        guaranteed wasted refit per adoption.
        """
        plane = as_plane(view)
        members = pool_members(plane, self.footing_id, self.region)
        keys = {self.pool,
                region_pose_collection_key(self.footing_id, self.region),
                region_evidence_collection_key(self.footing_id, self.region),
                *members}
        if self._labels.enriches:
            keys.add(COLLECTION_CERTIFIED)
        return tuple(sorted(keys))

    def run(self, view: SolveView, identity: AttemptIdentity,
            progress: ProgressSink) -> WorkResult:
        plane = as_plane(view)
        members = pool_members(plane, self.footing_id, self.region)
        progress.emit(1, "arm")
        if not members:
            return WorkResult(outcome=OUTCOME_REFUSED_PREFIX + "no_members")
        # The label field at FIRE TIME, over COMMITTED certificates only
        # (the prospective-only law): nothing in flight can reach a
        # frontier assembled from the pinned generation's index.
        reference = self._labels.field(plane)
        search, validation, heldouts = region_fit_inputs(
            plane, reference, self.footing_id, members, progress=progress)
        enriched = self._enriched_count(plane, members)
        if search.llr.size and validation.llr.size:
            fit = detect.fit_context(
                detect.ContextObservations(
                    str(self.pool), search.llr, search.counts,
                    search.labels, search.site_ids),
                detect.ContextObservations(
                    str(self.pool), validation.llr, validation.counts,
                    validation.labels, validation.site_ids))
            offsets = fit.offsets
            reason = fit.reason
            adopted = fit.adopted
            supports = (fit.n_search_0, fit.n_search_1,
                        fit.n_validation_0, fit.n_validation_1)
            losses = (fit.baseline_validation_logloss,
                      fit.candidate_validation_logloss)
        else:
            # One pooled side is EMPTY: v1's exact sidecar case — the
            # carried observation type cannot hold zero rows, so the
            # refusal reason is derived by the same cascade the floors
            # inside ``fit_context`` state.
            offsets = np.zeros(CTX_BINS, np.float64)
            reason = _floor_reason(search, validation)
            adopted = False
            supports = (*search.unique_class_support,
                        *validation.unique_class_support)
            losses = (None, None)
        progress.emit(1, "fit")
        # F1 (ruling J2-1): the per-window held-out losses v1's ownership
        # freeze ranks by — measured on the CORRECTED window where this
        # fit adopts, on the marginal one where it refuses. Same pass,
        # same arrays, no second read.
        windows = member_window_losses(heldouts, offsets if adopted else None)
        writes, blobs = self._writes(plane, members, offsets, reason,
                                     adopted, supports, losses, enriched,
                                     windows)
        outcome = (OUTCOME_ADOPTED if adopted
                   else OUTCOME_REFUSED_PREFIX + reason)
        return WorkResult(outcome=outcome, writes=writes, blobs=blobs)

    # -- internals ---------------------------------------------------------

    def _enriched_count(self, plane: PlaneView,
                        members: tuple[ResourceKey, ...]) -> int:
        """Certified tiles whose labels this pool's pages could see.

        The pool is region-scoped and the frontier is page-scoped, so the
        honest count is the frontier restricted to the pages the members
        actually address — which is what moved this pool's label
        population, and what the pool record then carries forward as its
        high-water mark.
        """
        if not self._labels.enriches:
            return 0
        index = plane.index()
        pages = {index.poses[pose].page for pose in members
                 if pose in index.poses}
        frontier = self._labels.frontier(plane)
        return sum(1 for address in frontier.by_address
                   if address[0] in pages)

    def _writes(self, plane: PlaneView, members: tuple[ResourceKey, ...],
                offsets: np.ndarray, reason: str, adopted: bool,
                supports: tuple[int, int, int, int],
                losses: tuple[float | None, float | None],
                enriched: int,
                windows: dict[ResourceKey, float],
                ) -> tuple[tuple[Write, ...], tuple[StagedBlob, ...]]:
        params = np.concatenate((
            np.asarray(offsets, np.float64).ravel(),
            np.asarray(supports, np.float64),
            np.asarray([_ABSENT_LOSS if loss is None else float(loss)
                        for loss in losses], np.float64),
            np.asarray([1.0 if adopted else 0.0], np.float64),
            _member_loss_params(windows)))
        assert params.size == PARAM_LENGTH + 1 + _MEMBER_STRIDE * len(windows)
        blob = stage_array(params)
        key = calibration_key(self.pool, CTX_ALGORITHM, blob.ref.sha256)
        writes: list[Write] = []
        blobs: list[StagedBlob] = []
        pool = self._pool_record(plane, members, supports, enriched)
        if pool is not None:
            writes.append(Write(self.pool, pool))
        if plane.record(key) is None:
            delta = (0.0 if losses[0] is None or losses[1] is None
                     else float(losses[1]) - float(losses[0]))
            writes.append(Write(key, CalibrationRecord(
                scope=self.pool, algorithm=CTX_ALGORITHM,
                params_ref=blob.ref,
                heldout=HeldoutGate(
                    adopted=adopted, logloss_delta=delta,
                    refusal_reason=None if adopted else reason))))
            blobs.append(blob)
        return tuple(writes), tuple(blobs)

    def _pool_record(self, plane: PlaneView,
                     members: tuple[ResourceKey, ...],
                     supports: tuple[int, int, int, int],
                     enriched: int) -> LabelPool | None:
        """The grown pool, or None when nothing about it moved.

        Members are recorded by WINDOW id (the record's own field), and
        both the member set and the per-kind counts are merged MONOTONE:
        the F-08 transition law says a pool only grows, and a quarantine
        that shrank the live population must not look like a shrinking
        pool — the live population is derived at fire time, the record is
        the high-water mark that versions it.

        The certified count rides the SAME field (P2): enrichment changes
        the pool's member set, so it moves the pool record's version
        through the mechanism that already exists, and adds no record
        kind. It merges by the same high-water rule as the rest.
        """
        windows = {ResourceKey(KIND_WINDOW, pose.parts[:WINDOW_KEY_PARTS])
                   for pose in members}
        current = plane.record(self.pool)
        counts = {"ctx-search": supports[0] + supports[1],
                  "ctx-validation": supports[2] + supports[3],
                  LABEL_KIND_CERTIFIED: enriched}
        if isinstance(current, LabelPool):
            windows |= set(current.member_window_ids)
            for kind, count in current.label_site_count_by_kind:
                counts[kind] = max(counts.get(kind, 0), count)
        proposed = LabelPool(
            pool_id=PoolId(self.pool.parts[0]),
            member_window_ids=tuple(sorted(windows)),
            label_site_count_by_kind=tuple(sorted(counts.items())))
        return None if proposed == current else proposed


# ---------------------------------------------------------- the provider

class CtxCalibrationProvider:
    """One fit-descriptor per (footing, region) with a committed member.

    PROVIDERS CA2 as a provider: subject = the pool key, route =
    ``ctx-pava-v1``, scope = the footing (the correction is
    footing-scoped), premium = the footing's lane term so a coarse
    region's fit still runs before a fine region's inside one order.
    The member-set half of the census's spend identity is the worker's
    read-set (§7: the read-set IS the identity — the pool key, the
    region's pose collection and the member poses), so a new member or a
    condemnation re-arms the descriptor and an unchanged pool is idle by
    the ordinary spend-once test.
    """

    family = FAMILY_CALIBRATION
    sources: tuple[str, ...] = ("pose", "collection:poses-region")

    PROVIDER_ID = "calibration-ctx-v1"

    def __init__(self, row: FormatRowSpec, *,
                 provider_id: str = PROVIDER_ID,
                 certified_labels: bool = False) -> None:
        self.provider_id = provider_id
        self.spec: TileFormat = tile_format_for(row)
        # ONE label source per provider: it owns both mint-once caches
        # (per certificate, per frontier), so their lifetime is the
        # session's and a fit pays only for certificates that ARRIVED.
        # Enrichment is DIALED, default off — the fold ruling and its
        # measured basis live on FormatOnlyLabels' docstring.
        source = (CertifiedLabelSource if certified_labels
                  else FormatOnlyLabels)
        self._labels = source(V1ReferenceField(self.spec))

    def expand(self, view: SolveView,
               request: ExpansionRequest) -> tuple[WorkDescriptor, ...]:
        plane = as_plane(view)
        return tuple(
            request.mint(
                FAMILY_CALIBRATION, ctx_pool_key(footing_id, region),
                ROUTE_CTX, profile=str(footing_id),
                premium=LANE_COST_PER_RUNG * plane.footing_depth(footing_id))
            for footing_id, region in pool_scopes(plane))

    def worker(self, view: SolveView,
               descriptor: WorkDescriptor) -> CtxFitWorker:
        plane = as_plane(view)
        scopes = {ctx_pool_key(footing_id, region): (footing_id, region)
                  for footing_id, region in pool_scopes(plane)}
        footing_id, region = scopes[descriptor.subject]
        return CtxFitWorker(descriptor.subject, footing_id, region,
                            self._labels)


__all__ = [
    "CTX_ALGORITHM", "CtxCalibrationProvider",
    "CtxFitWorker",
    "FAMILY_CALIBRATION", "OUTCOME_ADOPTED", "OUTCOME_REFUSED_PREFIX",
    "CTX_BINS", "PARAM_LENGTH", "ROUTE_CTX", "binary_logloss",
    "ctx_pool_id", "ctx_pool_key",
    "member_digest", "member_window_losses",
    "pool_members", "pool_of_evidence", "pool_scopes", "pose_pool_scope",
    "published_losses", "region_fit_inputs", "region_populations",
]

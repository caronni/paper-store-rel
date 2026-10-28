"""solve's KEY vocabulary: a durable id IS its defining values (§6).

Split out of ``records.py`` at H4 W2 (the file-cap seam), and it is a
functional one rather than a convenient one: nothing here is a record.
These are the ``core.keys`` slot declarations for solve's six composite
kinds, the named builders call sites read, the parsers that take them
apart, and the two derived COLLECTIONS a worker subscribes to when the
member it wants does not exist yet. They depend on ``core`` and on
``capture``'s region key alone — never on a record dataclass — which is
what makes this the one clean cut through that module: the dependency
runs one way, ``records`` on THIS module and never the reverse.

``records.py`` re-exports every name below, deliberately: the key
vocabulary is part of what "solve's records" means to a caller, and a
seam taken for a line cap must not become a second address every
importer has to learn. New code may import from either.

The reasoning for each key's SHAPE — why a window carries its region in
the middle and an evidence key its pose at the end, why arities are
derived from the specs, why an affine term is canonicalised at
construction — lives with the declaration it belongs to, below.
"""
from __future__ import annotations

from ..capture import KIND_REGION, REGION_KEY_PARTS
from ..core import (FootingId, KeyEmbed, KeyField, KeySpec, MalformedKeyError,
                    PoolId, ResourceKey, StreamId, build_key, collection_key,
                    parse_key)

KIND_TILE = "tile"
KIND_POSE = "pose"
KIND_WINDOW = "window"
KIND_EVIDENCE = "evidence"
KIND_POOL = "pool"
KIND_CALIBRATION = "calibration"

#: Native-pixel decimals a committed affine term carries (W0-B measured,
#: RATIFIED 2026-08-15: noise collapses, 3.245e-5 stays 32 quanta wide).
POSE_TERM_DECIMALS = 6


# --------------------------------------------------------------------------
# keys — a durable id IS its defining values (root DESIGN §6)
# --------------------------------------------------------------------------

#: The composite kinds, declared once each as ``core.keys`` slots. Slot
#: ORDER is data because these kinds really do differ in it — a window
#: carries its embedded region in the MIDDLE, an evidence key its pose at
#: the END, a pose and a hint their window at the START — and the
#: kind-and-arity guard four of these builders used to spell out by hand
#: now lives once, in ``core.keys``, where the two structural rules are
#: stated. The named wrappers below are what call sites read and where
#: each key's reasoning lives.
#:
#: The fixed arities are DERIVED from the specs rather than restated:
#: each is "the embedded id's parts, plus this kind's own values", which
#: is what lets a composite key be parsed positionally and makes the
#: embedding injective without a delimiter or an escape — and a
#: hand-written second spelling of it is a drift waiting to happen.
TILE_SPEC = KeySpec(KIND_TILE, (
    KeyField("page", cast=int), KeyField("ty", cast=int),
    KeyField("tx", cast=int), KeyField("stream")))
WINDOW_SPEC = KeySpec(KIND_WINDOW, (              # footing, region, extent
    KeyField("footing_id"), KeyEmbed("region", KIND_REGION, REGION_KEY_PARTS),
    KeyField("extent_cells", 4, cast=int)))
WINDOW_KEY_PARTS = WINDOW_SPEC.arity

POSE_SPEC = KeySpec(KIND_POSE, (                  # window, page, affine
    KeyEmbed("window", KIND_WINDOW, WINDOW_KEY_PARTS),
    KeyField("page", cast=int), KeyField("native_affine", 6, cast=float)))
POSE_KEY_PARTS = POSE_SPEC.arity

EVIDENCE_SPEC = KeySpec(KIND_EVIDENCE, (          # footing, page, tile, pose
    KeyField("footing_id"), KeyField("page", cast=int),
    KeyField("ty", cast=int), KeyField("tx", cast=int), KeyField("stream"),
    KeyEmbed("pose", KIND_POSE, POSE_KEY_PARTS)))
EVIDENCE_KEY_PARTS = EVIDENCE_SPEC.arity


def tile_key(page: int, ty: int, tx: int, stream: StreamId) -> ResourceKey:
    """The work key of §2: ``(page, ty, tx, stream)``."""
    return build_key(TILE_SPEC, page=page, ty=ty, tx=tx, stream=stream)


def parse_tile_key(key: ResourceKey) -> tuple[int, int, int, str]:
    values = parse_key(TILE_SPEC, key)
    return (values["page"], values["ty"], values["tx"], values["stream"])


def window_key(footing_id: FootingId, region: ResourceKey,
               extent_cells: tuple[int, int, int, int]) -> ResourceKey:
    """One working set of cells: its footing, its region, its extent."""
    return build_key(WINDOW_SPEC, footing_id=footing_id, region=region,
                     extent_cells=extent_cells)


def parse_window_key(key: ResourceKey) -> tuple[FootingId, ResourceKey,
                                                tuple[int, int, int, int]]:
    """The footing, region and extent a window key names."""
    values = parse_key(WINDOW_SPEC, key)
    extent = values["extent_cells"]
    return (FootingId(values["footing_id"]), values["region"],
            (extent[0], extent[1], extent[2], extent[3]))


def canonical_affine_terms(terms: tuple[float, ...]) -> tuple[float, ...]:
    """The six terms as a committed pose carries them (W0-B, pose v4).

    Two canonicalisations, neither a tolerance: :data:`POSE_TERM_DECIMALS`
    native-pixel decimals, and a normalised negative zero (``repr``
    distinguishes it, so ``-0.0`` would mint a second key for one fit).
    """
    return tuple(round(float(term), POSE_TERM_DECIMALS) + 0.0
                 for term in terms)


def pose_key(window: ResourceKey, page: int,
             native_affine: tuple[float, ...]) -> ResourceKey:
    """Committed geometry: the window it fits, and the fit itself."""
    return build_key(POSE_SPEC, window=window, page=page,
                     native_affine=native_affine)


def evidence_key(footing_id: FootingId, page: int, ty: int, tx: int,
                 stream: StreamId, pose: ResourceKey) -> ResourceKey:
    """§5.4: the footing and the single pose are IN the key."""
    return build_key(EVIDENCE_SPEC, footing_id=footing_id, page=page, ty=ty,
                     tx=tx, stream=stream, pose=pose)


def parse_evidence_key(key: ResourceKey) -> tuple[str, int, int, int, str,
                                                  ResourceKey]:
    values = parse_key(EVIDENCE_SPEC, key)
    return (values["footing_id"], values["page"], values["ty"], values["tx"],
            values["stream"], values["pose"])


def pool_key(pool_id: PoolId) -> ResourceKey:
    return ResourceKey(KIND_POOL, (pool_id,))


def region_pose_collection_key(footing_id: FootingId,
                               region: ResourceKey) -> ResourceKey:
    """Every committed pose of one (footing, region) — the pool's wake.

    The region-scoped sibling of :func:`pose_collection_key`, declared for
    H5's calibration reduce: a region ctx fit's label pool is fed by the
    committed placements of one footing in one region, and a pose key
    cannot be named before the fit exists, so membership arrival has to be
    a version bump on a key the fit already declared. The pose family
    joins it in ``records._pose_collections``; the version is the member
    count, derived by the resource table like every collection's.
    """
    if region.kind != KIND_REGION:
        raise MalformedKeyError(f"not a region key: {region}")
    return collection_key("poses-region", footing_id, *region.parts)


def region_evidence_collection_key(footing_id: FootingId,
                                   region: ResourceKey) -> ResourceKey:
    """Every committed PIECE of one (footing, region) — the ctx pool's
    other wake (F2a review fix, 2026-08-23).

    The region-scoped sibling of :func:`evidence_collection_key`, and it
    exists for one measured reason. A ctx fit's population is the pieces
    its member poses own, but until this key existed the fit subscribed
    only to the pool, the region's POSE collection and the member pose
    keys — so a commit that adds PIECES without adding a pose moved
    nothing the fit reads. That commit is exactly the re-read
    (:mod:`holo2.solve.resample`), which emits at a live pose and
    deliberately writes no pose record: measured on the archived states,
    0 of 4 e029 pools and 0 of 4 Xerox pools had any fit that had seen a
    re-read's pieces, and 0 of 255 Xerox re-read poses had a published
    window loss. v1 re-runs the affected region's coupled fit after
    re-sampling (``_payload_reuse.sample_refined_reusing_generation``);
    this is that replay in the pull model's own idiom.

    IT COSTS ALMOST NOTHING ON THE ORDINARY PATH, which is why it is the
    right key rather than a finer one: a placement emission commits its
    pose and its pieces in ONE batch, so this collection bumps in the
    same commit ``region_pose_collection_key`` already bumps in and the
    fit wakes once either way. The only commits it adds a wake for are
    the ones that add pieces alone — the re-read, and nothing else in
    the tree writes evidence.
    """
    if region.kind != KIND_REGION:
        raise MalformedKeyError(f"not a region key: {region}")
    return collection_key("evidence-region", footing_id, *region.parts)


def calibration_collection_key(pool: ResourceKey) -> ResourceKey:
    """The ADOPTED region fits of one label pool — versioned on adoption.

    The ONE region-scoped key a payload decode subscribes to beside its
    own tile's evidence (H5-PLAN, subscription scoping): membership is
    declared by the calibration family (``records._calibration_collections``)
    and admits ONLY pool-scoped fits whose held-out gate ADOPTED, so the
    version moves exactly when an adoption commits — never per label,
    never on a pool write, never on a refused fit.
    """
    if pool.kind != KIND_POOL:
        raise MalformedKeyError(f"not a pool key: {pool}")
    return collection_key("calibration", *pool.parts)


def calibration_key(scope: ResourceKey, algorithm: str,
                    params_sha256: str) -> ResourceKey:
    """One fit: its scope, the algorithm, and the parameters themselves.

    The parameters are bulk, so they enter the id as the content address
    the sidecar already gave them (the one sanctioned hash). Two fits of
    one window that differ at all are two calibrations; two that agree
    exactly are one, which is the right answer for a record committed
    evidence cites by name.
    """
    return ResourceKey(KIND_CALIBRATION,
                       (scope.kind, *scope.parts, algorithm, params_sha256))


#: Every CERTIFIED work key. Certificates are terminal and immutable
#: (L5), so the member count is an exact digest of the close's input —
#: which is what lets a close consult arm in O(1) instead of
#: O(certified) (M11).
COLLECTION_CERTIFIED = collection_key("certified")


def evidence_collection_key(key: ResourceKey) -> ResourceKey:
    """The observation pieces standing on one work key.

    This is the resource a payload worker depends on but cannot name
    piecewise: an evidence key that does not exist yet has no version to
    bump. Naming the collection makes the arrival of a NEW piece an
    ordinary version bump on a key the worker already declared.
    """
    if key.kind != KIND_TILE:
        raise MalformedKeyError(f"not a work key: {key}")
    return collection_key("evidence", *key.parts)


def pose_collection_key(window: ResourceKey) -> ResourceKey:
    """Every committed pose of one window — how placement subscribes to them.

    The sibling of :func:`evidence_collection_key`, and for the same
    reason: since the identity law a pose key IS its window, its page and
    its six affine terms, so a worker that wants "the poses of that
    window" cannot write down a key for a fit nobody has made yet.
    Naming the collection turns the arrival of a new pose into an
    ordinary version bump — the version IS the member count — on a key
    the subscriber already declared.

    It had no subscriber until worklist B7 (RULED 2026-08-12) moved
    ``RealPlacementWorker.read_keys`` off its per-sibling
    ``pose_key(...)`` enumeration, which could only ever name the poses
    that already existed.
    """
    return collection_key("poses", *window.parts)


__all__ = [
    "COLLECTION_CERTIFIED", "EVIDENCE_KEY_PARTS", "EVIDENCE_SPEC",
    "KIND_CALIBRATION", "KIND_EVIDENCE", "KIND_POOL", "KIND_POSE",
    "KIND_TILE", "KIND_WINDOW", "POSE_KEY_PARTS", "POSE_SPEC",
    "POSE_TERM_DECIMALS", "TILE_SPEC", "WINDOW_KEY_PARTS", "WINDOW_SPEC",
    "calibration_collection_key", "calibration_key",
    "canonical_affine_terms", "evidence_collection_key",
    "evidence_key", "parse_evidence_key", "parse_tile_key",
    "parse_window_key", "pool_key", "pose_collection_key", "pose_key",
    "region_evidence_collection_key", "region_pose_collection_key",
    "tile_key", "window_key",
]

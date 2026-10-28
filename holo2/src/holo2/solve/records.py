"""RECORDS solve owns: the tile map, geometry, evidence, calibration.

Every family here is written by a solve worker — the placement family
mints poses, hints, windows, tile addressing and observation pieces; the
payload family mints certificates; the calibration reduce mints label
pools and calibration fits. R3's ownership rule is "the package that
WRITES a family owns its schema", so this is where they live and where
their versions are bumped.

* :class:`TileRecord` (+ :class:`MintRef`) — §5.2, the logical authority,
  one per ``(page, ty, tx, stream)``. Its display vocabulary lives in
  ``tilemap`` now, where derived views live (``TileState``, below).
* :class:`PoseRecord`, :class:`WindowRecord` — §5.3, the physical
  plane's committed geometry.
* :class:`EvidenceObservation` — §5.4, the durable payload atom.
* :class:`LabelPool`, :class:`CalibrationRecord` (+ :class:`HeldoutGate`)
  — §5.4, the calibration reduce's scope and its fits.
* ``LatticeSeedRecord`` — H4 W1/R5's per-(footing, region) lattice seed,
  declared with its ruling in ``solve/lattice_seed.py``.

The WALL-SIDE half — the F-08 transition laws, the F-07 references, the
M4 collection memberships and the ``record_families`` registration —
moved to ``solve/families.py`` at H5 P1, when the calibration family's
collections hook took this module past the 1000-line cap (a seam signal,
and it named the joint the cut runs along: what a record IS stays here,
how the wall must treat it lives there; the dependency runs families ->
records and never back, exactly like the ``keys.py`` seam).

The KEYS these records are stored under moved to ``solve/keys.py`` at H4
W2 — a file-cap seam taken at the one place this module cuts cleanly,
since a key declaration depends on ``core`` and on ``capture``'s region
key and never on a record. Every name is re-exported here, so nothing
about how a caller reaches them changed.
§5.3's candidate facts have NO family here: H4 W2's pull model ruled a
hint a scheduling annotation rather than a fact, so the steers a window
acts on are computed at fire time from the committed poses around it
(``place_job.consult``) and nothing about them crosses the wall.

Shape change, H4 W1 (2026-08-15): **``PoseRecord.native_affine`` is
CANONICAL** (pose family **v4**) — :func:`canonical_affine_terms` rounds
at construction, so key and value cannot disagree and the fitter's noise
terms (measured max 9.74e-7) collapse instead of minting distinct keys.

Shape changes, R3
-----------------
* **``PoseRecord.page``** (v2). One pose = one page (user-confirmed). The
  page a pose addresses was durable only *indirectly*, in the keys of the
  observation pieces it produced, so the done projection had to re-derive
  it by scanning evidence keys and a pose that observed nothing had no
  page at all. It is now a field, validated in-domain by the family's
  structural validator against the session's declared page domain.
* **``EvidenceObservation.observed_ref``** (v2). §5.4 promises "the
  pieces' run-encoded cell masks"; the record carried only the LLR blob,
  so *observed-with-zero-LLR* and *never-observed* were the same bytes
  and the ownership freeze had to read a zero LLR as "unobserved". The
  mask is now durable beside the LLRs, as a packed bitset
  (:func:`pack_observed_cells`). The ownership freeze consumed it in W-B
  B6 (2026-08-12): ``take = piece.observed & ~owned`` — the contested
  cell's own value never decides who owns it. (This paragraph used to end
  "the freeze still keys on zero" — stale since B6, flagged by the
  sentinel audit, corrected here. It then read "no evidence value in
  owner selection anywhere", which F1 made too strong: the freeze's
  ORDER is v1's held-out log-loss, a statistic of the evidence at
  format-fixed sites — corrected 2026-08-23 on the F1 review.)

  **F1 (2026-08-23, ruling J2-2) put a HALO in the same blob.** The
  layout is the tile's 4,096-cell mask first, then the 260-cell ring
  frame's presence plane and its provisional-ink plane
  (:func:`pack_piece_observation`, :func:`ring_masks`) — 577 bytes where
  the bare mask is 512. **The blob is shape-versioned BY LENGTH, not by
  a family version**: the tile mask still occupies bits 0..4095, so
  every :func:`unpack_observed_cells` reader answers exactly what it
  answered before, and :func:`unpack_piece_halo` is the one function
  that looks at ``.size`` — a 512-byte blob answers ``None`` and its
  component falls back to tile-scoped ctx bins. A new plane in this blob
  therefore APPENDS and never inserts; anything that changes the meaning
  of the leading 4,096 bits is a family version, not a length.

Transition laws, F-08 (2026-08-13)
----------------------------------
Every family now declares how a standing record may move under its key,
enforced at the commit wall (``registry.check_transition``): tile is
monotone with frozen certified content (L5, unchanged); window's
scheduling states move freely and RETIRED is terminal; evidence and
calibration are FROZEN (an equal rewrite is a no-op, a differing one is
a refusal); pools only grow (§6.2). No wire shape moved in F-08 itself —
the wall merely stopped accepting writes nothing legal ever makes.

Shape change, the per-route payload split (2026-08-11)
------------------------------------------------------
* **``MintRef.route`` / ``MintRef.decoder_profile``** (tile family v2).
  The payload family mints one descriptor, one spend and one attempt per
  ROUTE, so a certificate can name the route and the decoder that
  produced it, and a lineage's false-accept exposure becomes a count over
  spends instead of an estimate over fires (HARDENING-SYSTEMIC-REVIEW
  P1). Both are required: unstated provenance is what the review was
  reading.
* **``TileRecord.baselined``** (same family version — same conceptual
  round, no committed state carries the earlier shape). The footings
  whose scan route ran a decoder on this key and failed, monotone by
  construction. It is the durable per-footing fact the retry route
  derives from: the tile-level ATTEMPTED state cannot say WHICH baseline
  failed, and deriving retries from it armed BP-150 on footings whose
  baseline never ran (the 2026-08-11 review's P1). A below-floor scan
  ran no decoder, so it contributes neither ATTEMPTED nor a baseline.

Shape change, ``TileRecord.state`` deleted (tile family **v4**)
---------------------------------------------------------------
F-06's last residue, closed 2026-08-14. The enum field carried no
behaviour the other fields cannot: **certified is the mint** (``minting
is not None`` — now the record's own :attr:`TileRecord.certified`
property), the eligibility domain is "a record exists and is not
certified" (``tilemap.TileMap.open_keys``), ADDRESSED is the record
existing, and retry eligibility has gated on the per-footing
``baselined`` fact since 2026-08-11 rather than on the tile-level
ATTEMPTED rank. What is left is a DISPLAY vocabulary — the operator's
tiles row and the pane-B chips — so :class:`tilemap.TileState` survives
there, derived: ATTEMPTED reads the spend ledger's payload CRC exposure
(``payload.attempted_work_keys``) plus ``baselined``, which is the
same fact the field recorded and the one place it was ever authoritative.

The three named constructors went with it. ``addressed_tile`` /
``attempted_tile`` / ``observed_tile`` disagreed about nothing but the
state they wrote, so they are one function again — :func:`carry_tile`,
the merge they always shared.

Shape changes, the elegance pass (2026-08-12)
---------------------------------------------
* **``MintRef.attempt_digest`` deleted** (tile family **v3**). Written at
  every mint, read nowhere in the tree — and the hash-free identity law
  (root DESIGN §6) already names the attempt structurally: the spend row
  is ``(payload, work key, route, scope)``, all of which the certificate
  and its key already carry. ``core.identity.identity_digest`` went with
  it; it had no other caller.
* **``WindowRecord.routes_spent`` / ``RouteSpend`` deleted** (window
  family **v3**). Declared from §5.3 and never written by any layer (the
  one writer in the tree was a test fixture), while the ledger held the
  authority the whole time. Deleted rather than carried as a standing
  open question, per the freshness doctrine; a per-window projection is a
  read over the ledger the day a consumer wants one.

Shape change, the hash-free identity law (2026-08-11)
-----------------------------------------------------
A durable id IS its defining values, kept structured (root DESIGN §6),
so the digest ids are gone and **the key is the id**:

* window = ``(footing, *region key parts, extent)`` — 11 parts;
* pose = ``(*window key parts, page, *native affine)`` — 18 parts, the
  affine terms as ``repr(float)``, which round-trips;
* calibration = ``(scope kind, *scope key parts, algorithm, params
  content address)`` — the parameters are bulk, and a blob's content
  address is the one place hashing IS the mechanism, so two different
  fits of one window are two different calibrations by construction;
* evidence keeps its §5.4 shape with the pose's parts in the pose's
  place.

Every record that used to carry its id as a field carries the VALUES
instead, and ``resource_key()`` rebuilds the key from them; the families
validate the agreement at the commit wall and at load
(``core.require_own_key``, F-07's mechanism, adopted by every family in
this module but one — a ``TileRecord`` carries no component of its work
key, so the kind guard at the wall is already the whole check). Arities
are fixed per kind, which is what makes the embedding of one id inside
another injective by construction.

Choices where §5 is silent
--------------------------
* ``EvidenceObservation``: §5.4 writes ``key: (footing_id, page, ty, tx,
  stream, pose_id)``. The tuple is expanded into named fields of exactly
  those components (plus ``resource_key()``, which rebuilds the key). The
  point of §11 is that the footing is *in the key* structurally; naming
  the components makes an illegal cross-aperture record unrepresentable
  at the record level too, not just at the store level. The footing and
  page the pose parts repeat are deliberate: the law that a piece of
  evidence names ONE footing is visible in the key's own shape.
* **A window's split lineage is not part of its id.** ``window_id_for``
  digested one, and nothing ever passed a non-empty value. A split
  child's working set is its extent, so its extent names it; where the
  lineage becomes durable (OR-9), it belongs on the record as
  provenance. Should it ever have to enter an id, the rule is the
  keys-module invariant: variable-length components go LAST.
* ``LabelPool.label_site_count_by_kind``: §5.4 types it ``dict[str,
  int]``. A mutable dict inside a frozen record would silently break the
  equality that version-bump-iff-changed rests on, so it is a sorted
  tuple of ``(kind, count)`` pairs with the same name;
  ``label_site_counts()`` returns the mapping.
* ``TileRecord`` has no ``key`` field: the authoritative spend mechanism
  is the store's durable spend ledger (``core.identity``), and the work
  key names the row.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from ..core import (BlobRef, CertificateConflict, FootingId,
                    PoolId, Record, ResourceKey,
                    StreamId, require_sorted_unique)
# The printed tile's cell extent: the halo layout below is a frame around
# it, so the blob's byte count is a function of the FORMAT's tile and not
# of anything solve chose (F1, 2026-08-23).
from ..format import TILE_CELLS
# The key vocabulary, RE-EXPORTED on purpose (``solve/keys.py``'s own
# docstring says why): it was cut out of this module at the file-cap
# seam, and a caller who reads "solve's records" still expects to find
# the keys those records are stored under here.
from .keys import (COLLECTION_CERTIFIED, EVIDENCE_KEY_PARTS,
                   EVIDENCE_SPEC, KIND_CALIBRATION, KIND_EVIDENCE,
                   KIND_POOL, KIND_POSE, KIND_TILE, KIND_WINDOW,
                   POSE_KEY_PARTS, POSE_SPEC, POSE_TERM_DECIMALS,
                   TILE_SPEC, WINDOW_KEY_PARTS, WINDOW_SPEC,
                   calibration_collection_key, calibration_key,
                   canonical_affine_terms,
                   evidence_collection_key, evidence_key,
                   parse_evidence_key, parse_tile_key, parse_window_key,
                   pool_key, pose_collection_key, pose_key,
                   region_evidence_collection_key,
                   region_pose_collection_key, tile_key,
                   window_key)

# --------------------------------------------------------------------------
# enums and nested value types
# --------------------------------------------------------------------------


class WindowStatus(Enum):
    """§5.3 — OUTCOMES ONLY since the pull model (H4 W2, ruling Q2).

    A window record says what HAPPENED to a window: it was placed
    (``ACTIVE``, and its pose is the witness) or it was retired with a
    reason. Every scheduling state it used to carry is gone — ``PENDING``
    was never written, and ``SLEEPING`` was the word route's staging fact
    ("the cheap half is spent"), which is now the pull job's in-memory
    stage memory and never crosses the wall. The user's ruling in one
    line: "WINDOWRECORD = OUTCOME ONLY. Placed-by and retirement reason;
    every scheduling state sheds."
    """

    ACTIVE = "active"
    RETIRED = "retired"


@dataclass(frozen=True)
class MintRef:
    """Which attempt, which ROUTE and which pose minted a certificate (§5.2).

    ``route`` and ``decoder_profile`` are the provenance the review found
    missing (HARDENING-SYSTEMIC-REVIEW P1, "one spend hides multiple CRC
    exposures"). With one descriptor per route the route is a durable
    NAME, not a label: the spend that minted this certificate is the
    ledger row ``(payload, this work key, this route, its scope)``, and
    the profile states the decoder that actually ran (BP-60 on a scan or
    union, BP-150 on a retry). Neither may be empty — a certificate whose
    route and decoder are unstated is one nobody can audit, and that is
    the state this record was in.

    ``contributors`` (M10) is the full provenance SET where one pose is
    not the whole story — a cross-capture union is minted from several
    observation pieces, and a contradiction quarantines the placements
    that contributed to it. ``pose_id`` stays the primary witness (the
    ordering rule that picks it is the ownership freeze's); an empty
    ``contributors`` means "the primary witness is the whole set".

    There is no ``attempt_digest`` (tile family v3, the hash-free
    identity law): it was written at every mint and read nowhere, and
    what it digested — the attempt's read-set identity — is already NAMED
    structurally by the ledger row ``(payload, this work key, this route,
    its scope)``. A digest of values the key already carries is an
    identity nobody can read back, which is exactly what §6 retired.
    """

    pose_id: ResourceKey
    route: str
    decoder_profile: str
    contributors: tuple[ResourceKey, ...] = ()

    def __post_init__(self) -> None:
        if not self.route or not self.decoder_profile:
            raise ValueError(
                "MintRef names the route and the decoder that minted "
                "the certificate")
        require_sorted_unique(self.contributors, "MintRef.contributors")


@dataclass(frozen=True)
class HeldoutGate:
    """§5.4: adopted | refused(reason), with the logloss delta."""

    adopted: bool
    logloss_delta: float
    refusal_reason: str | None = None


# --------------------------------------------------------------------------
# durable records
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TileRecord:
    """§5.2, one per ``(page, ty, tx, stream)``. Certified is terminal.

    ``baselined`` names the footings whose scan route ran a decoder here
    and failed — the durable fact the retry route derives from. Like
    ``observed_by`` it only ever gains members; unlike ``observed_by`` it
    is written exclusively by a failing scan, because "a baseline exists"
    is a statement about a decoder having run, not about evidence having
    been seen.

    There is no ``state`` (tile family v4): a certificate IS its mint, so
    the rank the field held is derivable and the vocabulary that reads it
    is a display view (``tilemap.TileState``).
    """

    minting: MintRef | None = None
    bits_ref: BlobRef | None = None
    metadata_bit: int | None = None
    observed_by: tuple[FootingId, ...] = ()   # footing ids, sorted unique
    baselined: tuple[FootingId, ...] = ()     # footing ids, sorted unique

    @property
    def certified(self) -> bool:
        """A certificate is the mint that made it (§5.2, L5).

        The mint names the route, the decoder and the pose, and nothing
        but a certifying attempt writes one — so "certified" is not a
        label beside the provenance, it IS the provenance being there.
        """
        return self.minting is not None

    def __post_init__(self) -> None:
        require_sorted_unique(self.observed_by, "TileRecord.observed_by")
        require_sorted_unique(self.baselined, "TileRecord.baselined")
        if self.metadata_bit is not None and self.metadata_bit not in (0, 1):
            raise ValueError("TileRecord.metadata_bit is one LDPC bit")


@dataclass(frozen=True)
class PoseRecord:
    """§5.3, committed geometry (trust tier 2); existence = audit witness.

    ``page`` is the one printed page this pose addresses (R3). A window
    that straddles pages fails its fit and subdivides (§5.4), so exactly
    one page per pose is the format's own rule, not a simplification.

    Window, page and affine ARE the pose's identity; ``footing_id`` is
    the window's own footing, kept here because every reader wants it and
    the validator proves the two agree.

    The affine is CANONICALISED here (v4, :func:`canonical_affine_terms`)
    rather than at the key builder: that is what makes key and value
    agree by construction.

    ``quarantined`` is W5's marking (pose family **v5**): this placement
    contributed to, or is contradicted by, an address-word
    contradiction. It is NOT part of the key — a condemned pose is the
    SAME geometry, judged — which is exactly why the family had to grow
    a transition law (below) after four versions of needing none. The
    consult never offers a marked pose (``quarantine.is_quarantined``),
    and ``tilemap.project_done`` never asks: done pixels are
    certificate-backed, so quarantining moves none of them (ruling 1).
    """

    window_id: ResourceKey
    footing_id: FootingId
    page: int
    native_affine: tuple[float, ...]
    quarantined: bool = False

    def resource_key(self) -> ResourceKey:
        return pose_key(self.window_id, self.page, self.native_affine)

    def __post_init__(self) -> None:
        if len(self.native_affine) != 6:
            raise ValueError("PoseRecord.native_affine is 6 affine terms")
        if self.page < 0:
            raise ValueError("PoseRecord.page must be a page index >= 0")
        object.__setattr__(self, "native_affine",
                           canonical_affine_terms(self.native_affine))


@dataclass(frozen=True)
class WindowRecord:
    """§5.3. The footing, region and extent ARE the window's name.

    It carries no ``routes_spent`` (v3): §5.3 sketched one, nothing wrote
    it — the durable spend ledger is the authority (``core.identity``),
    and a record that changed on every re-arm would turn the wake graph
    into a treadmill; a per-window projection is a READ over it. v4
    changes no FIELD: a window is named by its EXTENT, so the flush-shift
    ruling renamed the population and clipped states refuse at open.

    **v5 makes it an OUTCOME record** (H4 W2, ruling Q2): the status
    vocabulary shed its scheduling values, so this record now answers one
    question — what happened to this window — and nothing about what is
    scheduled next. Readiness, the tried set, stage memory and priority
    live in the placement scheduler, in memory, and are rebuilt on resume
    from plans minus placed minus covered.
    """

    footing_id: FootingId
    region_id: ResourceKey
    extent_cells: tuple[int, int, int, int]
    status: WindowStatus
    retired_reason: str | None = None

    def __post_init__(self) -> None:
        # F-08's "illegal sum states" half: the reason rides exactly the
        # terminal status — a retirement always says why (§3 glossary:
        # windows end "retired(reason)"), and a live window carries none.
        if (self.retired_reason is not None) != (
                self.status is WindowStatus.RETIRED):
            raise ValueError(
                "WindowRecord.retired_reason rides exactly the RETIRED "
                f"status (got {self.status.value!r} with reason "
                f"{self.retired_reason!r})")

    def resource_key(self) -> ResourceKey:
        return window_key(self.footing_id, self.region_id, self.extent_cells)


@dataclass(frozen=True)
class EvidenceObservation:
    """§5.4, the durable payload atom: bounded calibrated LLRs (L2).

    Exactly one footing and exactly one pose — single provenance by
    construction, which is what makes an illegal cross-aperture sum
    unrepresentable rather than merely validated (§11).

    ``observed_ref`` is the packed cell mask of what this pose actually
    SAW inside the tile (R3): a cell outside it has no evidence, which is
    a different fact from a cell whose calibrated LLR is 0.

    ``quarantined`` is W5's marking (evidence family **v4**): this piece
    came from a placement an address-word contradiction condemned, so
    the payload route never reads it again
    (``payload.route_evidence_keys``). It is the one field the F-08
    freeze below lets move, and only one way.
    """

    footing_id: FootingId
    page: int
    ty: int
    tx: int
    stream: StreamId
    pose_id: ResourceKey
    llr_ref: BlobRef
    observed_ref: BlobRef
    calibration_id: ResourceKey
    quarantined: bool = False

    def resource_key(self) -> ResourceKey:
        return evidence_key(self.footing_id, self.page, self.ty, self.tx,
                            self.stream, self.pose_id)

    def tile_key(self) -> ResourceKey:
        return tile_key(self.page, self.ty, self.tx, self.stream)


@dataclass(frozen=True)
class LabelPool:
    """§5.4, the calibration reduce's input scope."""

    pool_id: PoolId
    member_window_ids: tuple[ResourceKey, ...]
    label_site_count_by_kind: tuple[tuple[str, int], ...] = ()

    def resource_key(self) -> ResourceKey:
        return pool_key(self.pool_id)

    def __post_init__(self) -> None:
        require_sorted_unique(self.member_window_ids,
                              "LabelPool.member_window_ids")
        require_sorted_unique(
            tuple(kind for kind, _ in self.label_site_count_by_kind),
            "LabelPool.label_site_count_by_kind")

    def label_site_counts(self) -> dict[str, int]:
        return dict(self.label_site_count_by_kind)


@dataclass(frozen=True)
class CalibrationRecord:
    """§5.4/§8.4: one fit at one scope, adopted or refused by held-out.

    ``scope`` is the key of what the fit is over — a window today, a
    label pool when the reduce lands — and with the algorithm and the
    parameters' content address it IS this record's identity.
    """

    scope: ResourceKey
    algorithm: str
    params_ref: BlobRef
    heldout: HeldoutGate
    shrinkage_lambda: float | None = None

    def resource_key(self) -> ResourceKey:
        return calibration_key(self.scope, self.algorithm,
                               self.params_ref.sha256)


# --------------------------------------------------------------------------
# the tile-map JOIN — one algebra, both sides of the wall
# --------------------------------------------------------------------------


def join_tiles(key: ResourceKey | None, current: TileRecord,
               proposed: TileRecord) -> TileRecord:
    """``current ⊔ proposed``: the sets union, certified content verbatim.

    The tile map's whole algebra, written once because it is applied in
    two places (H4 W2, ruling 1): :func:`carry_tile` joins a gain onto
    the snapshot a FIRE read, and the family declares THIS FUNCTION as
    its wall-side ``merge`` hook, re-joining that proposal onto whatever
    stands when it lands. ⊔ is idempotent, commutative and associative,
    and a snapshot always sits BELOW what stands now, so both give the
    same value from any snapshot — which is the entire licence for
    re-applying a proposal at the wall instead of asking a
    compare-and-swap whether its key is still fresh.

    Why a certificate needs no ordering rule: certified content is
    IMMUTABLE (L5), so "carried verbatim" is total. A standing
    certificate's content stands whatever this proposal holds; an
    arriving one lands on an uncertified record. **Two certified
    contents that DISAGREE is a fatal integrity event** — the same
    :class:`CertificateConflict` the transition law raises today, raised
    here because a join that cannot join has nothing to return, and
    because a certificate is never voted on (L5).

    What DOES relax is the MINT of two AGREEING certificates.
    Concurrency made it reachable: two routes on one work key can both
    decode and both certify the same bits, naming different attempts in
    their ``MintRef``. That is corroboration, not contradiction, so the
    certified CONTENT — the symbol bits and the metadata bit — is what
    must agree, the standing mint keeps the provenance, and the loser's
    observation still merges in. Before the pool this could not happen:
    the loser's proposal was discarded on the tile key's version, which
    is the very compare-and-swap this hook replaces.
    """
    if current.certified and proposed.certified and (
            proposed.bits_ref != current.bits_ref
            or proposed.metadata_bit != current.metadata_bit):
        raise CertificateConflict(
            f"{key}: two certified decodes disagree — the record holds "
            f"{current.bits_ref} (metadata {current.metadata_bit}) and this "
            f"attempt certified {proposed.bits_ref} (metadata "
            f"{proposed.metadata_bit}); certified content may not change (L5)")
    held = current if current.certified else proposed
    return TileRecord(
        minting=held.minting, bits_ref=held.bits_ref,
        metadata_bit=held.metadata_bit,
        observed_by=tuple(sorted(set(current.observed_by
                                     + proposed.observed_by))),
        baselined=tuple(sorted(set(current.baselined + proposed.baselined))))


def carry_tile(current: Record | None,
               observed_gain: tuple[FootingId, ...],
               baseline: FootingId | None = None) -> TileRecord:
    """The fire side of the join: carry the record, GAIN the sets.

    Every writer makes this same write — a placement worker whose pose
    observed the tile, a payload worker whose decoder ran and failed
    (naming, on a scan, the ``baseline`` footing the retry route derives
    from), a below-floor or race-losing attempt that consumed evidence
    and certified nothing. They were three named constructors until tile
    family v4, and the state field was the only thing they disagreed
    about; what they always shared is this.

    Certified content is carried VERBATIM, so the transition law (L5)
    sees no edit, and the footing sets are UNIONED rather than replaced:
    a caller that passes only its new footings keeps the provenance done
    projection needs (§6), and a pre-merging caller is unaffected because
    the union is idempotent.

    Since H4 W2 the gain is expressed as a RECORD and handed to
    :func:`join_tiles`, which is what makes "the fire and the wall run
    one algebra" a fact of the code rather than a claim about it. A gain
    is never certified, so the conflict arm of the join is unreachable
    from here and no key is needed to name one.
    """
    return join_tiles(
        None, current if isinstance(current, TileRecord) else TileRecord(),
        TileRecord(observed_by=tuple(sorted(set(observed_gain))),
                   baselined=() if baseline is None else (baseline,)))


# --------------------------------------------------------------------------
# the observed-cell bitset
# --------------------------------------------------------------------------


def pack_observed_cells(mask: np.ndarray) -> np.ndarray:
    """Pack a boolean cell mask into the compact bitset a record refs.

    MSB-first within each byte (``np.packbits``' default and the tree's
    bit order everywhere else), row-major over the tile's cells. 64x64
    cells become 512 bytes instead of 4096, and identical masks — the
    common "this pose saw the whole tile" case — dedup to ONE blob,
    because the sidecar is content-addressed.
    """
    return np.packbits(np.ascontiguousarray(mask, dtype=bool))


def unpack_observed_cells(packed: np.ndarray,
                          shape: tuple[int, int]) -> np.ndarray:
    """The inverse of :func:`pack_observed_cells` at a declared shape."""
    count = int(shape[0]) * int(shape[1])
    bits = np.unpackbits(np.asarray(packed, np.uint8), count=count)
    return bits.astype(bool).reshape(shape)


# --------------------------------------------------------------------------
# the context halo (F1, ruling J2-2 "we implement v1", 2026-08-23)
# --------------------------------------------------------------------------
#
# v1 corrects the WHOLE 200x200 window before the ownership freeze
# (``_payload_context.apply_region_context:284-291``), so a payload cell
# takes the eight-neighbourhood it has inside its pose's window. holo2
# assembles per 64-cell tile, where the tile's outer ring is structurally
# bin -1 — MEASURED 6.15% of a tile's cells against v1's 1.56-2.11%
# (``scratch/holo2-catchup/detect/DETECTION-GAP.md`` H2). The missing
# information is exactly one cell deep: for each ring cell, the presence
# and the provisional ink of the neighbours JUST OUTSIDE the tile, as
# that pose saw them. That is the 260-cell frame below, and the sampler
# is the one worker that holds it (``place_shared.emit_placement`` has
# the whole window in hand).
#
# THE BLOB IS SHAPE-VERSIONED, NOT FAMILY-VERSIONED, deliberately.
# ``np.unpackbits(..., count=4096)`` reads the FIRST 4096 bits, so a
# haloed blob answers :func:`unpack_observed_cells` at the tile's shape
# with exactly what a pre-F1 blob answered. ``EvidenceObservation``'s
# JSON does not move, so no family version bumps and no state written
# before F1 refuses at open: such a state simply carries no halo and its
# decodes take the tile-scoped bins they always took. That mattered
# enough to choose: the archived real states are what F1's acceptance is
# measured on, and the W1-W6 instruments read them too.
# (``v1audit/C3-payload-calibration-ownership.md`` §10.5 recommended a
# record field and accepted the freshness break; this is the same
# semantics without it — see the F1 hand-off for the declared deviation.)

#: The one-cell frame around a tile: a 66x66 grid minus its middle.
HALO_FRAME = TILE_CELLS + 2
HALO_RING_CELLS = HALO_FRAME * HALO_FRAME - TILE_CELLS * TILE_CELLS
_RING_INDEX: np.ndarray = np.flatnonzero(
    ~np.pad(np.ones((TILE_CELLS, TILE_CELLS), bool), 1).ravel())
#: Packed blob sizes in bytes: the tile mask alone (pre-F1), and the tile
#: mask plus the ring's presence and ink planes (F1). The two differ, and
#: that difference IS the version tag :func:`unpack_piece_halo` reads.
OBSERVED_BYTES = -(-(TILE_CELLS * TILE_CELLS) // 8)
PIECE_HALO_BYTES = -(-(TILE_CELLS * TILE_CELLS + 2 * HALO_RING_CELLS) // 8)


def ring_masks(observed: np.ndarray, ink: np.ndarray,
               origin_yx: tuple[int, int], ty: int, tx: int,
               ) -> tuple[np.ndarray, np.ndarray]:
    """One tile's halo ring, read off a whole page-oriented placement.

    ``observed`` and ``ink`` are the placement's own window arrays in
    PAGE orientation with top-left ``origin_yx``; the pair returned is
    the ring of the frame centred on tile ``(ty, tx)``, in the row-major
    order :func:`unpack_piece_halo` reads back. A ring cell this
    placement never covered — off its own edge, or off the page — is
    absent, which is exactly what v1's window-scoped neighbourhood says
    about it: the tile cell beside it stays bin -1 there too.
    """
    origin_y, origin_x = origin_yx
    height, width = observed.shape
    present = np.zeros((HALO_FRAME, HALO_FRAME), bool)
    frame_ink = np.zeros((HALO_FRAME, HALO_FRAME), bool)
    ys = np.arange(HALO_FRAME) + ty * TILE_CELLS - 1 - origin_y
    xs = np.arange(HALO_FRAME) + tx * TILE_CELLS - 1 - origin_x
    rows = np.flatnonzero((ys >= 0) & (ys < height))
    cols = np.flatnonzero((xs >= 0) & (xs < width))
    if rows.size and cols.size:
        source = np.ix_(ys[rows], xs[cols])
        target = np.ix_(rows, cols)
        present[target] = np.asarray(observed, bool)[source]
        frame_ink[target] = np.asarray(ink, bool)[source]
    return (present.ravel()[_RING_INDEX], frame_ink.ravel()[_RING_INDEX])


def pack_piece_observation(observed: np.ndarray, ring_present: np.ndarray,
                           ring_ink: np.ndarray) -> np.ndarray:
    """The piece's cell mask FIRST, then the halo ring's two planes.

    Leading-bit compatibility is the whole layout rule: the tile mask
    occupies bits 0..4095, so every existing reader — every call of
    :func:`unpack_observed_cells` at the tile's shape — is unchanged.
    """
    return pack_observed_cells(np.concatenate((
        np.ascontiguousarray(observed, bool).ravel(),
        np.ascontiguousarray(ring_present, bool).ravel(),
        np.ascontiguousarray(ring_ink, bool).ravel())))


def unpack_piece_halo(packed: np.ndarray
                      ) -> tuple[np.ndarray, np.ndarray] | None:
    """A piece blob's halo frames, or ``None`` when it carries none.

    The two frames have the tile's own interior left FALSE: the
    interior's presence is the piece's own mask and its ink is the
    piece's own marginal, both of which the caller already holds, and
    neither of which this blob should be trusted to restate.
    """
    array = np.asarray(packed, np.uint8)
    if array.size != PIECE_HALO_BYTES:
        return None
    cells = TILE_CELLS * TILE_CELLS
    bits = np.unpackbits(array, count=cells + 2 * HALO_RING_CELLS)
    ring = bits[cells:].astype(bool)
    present = np.zeros(HALO_FRAME * HALO_FRAME, bool)
    ink = np.zeros(HALO_FRAME * HALO_FRAME, bool)
    present[_RING_INDEX] = ring[:HALO_RING_CELLS]
    ink[_RING_INDEX] = ring[HALO_RING_CELLS:]
    return (present.reshape(HALO_FRAME, HALO_FRAME),
            ink.reshape(HALO_FRAME, HALO_FRAME))


__all__ = [
    "COLLECTION_CERTIFIED", "CalibrationRecord", "EVIDENCE_KEY_PARTS",
    "EvidenceObservation", "HALO_FRAME", "HALO_RING_CELLS", "HeldoutGate",
    "KIND_CALIBRATION", "KIND_EVIDENCE",
    "KIND_POOL", "KIND_POSE", "KIND_TILE", "KIND_WINDOW",
    "LabelPool", "MintRef", "OBSERVED_BYTES", "POSE_KEY_PARTS",
    "POSE_TERM_DECIMALS", "PIECE_HALO_BYTES",
    "PoseRecord", "TileRecord", "WINDOW_KEY_PARTS",
    "WindowRecord", "WindowStatus", "calibration_collection_key",
    "calibration_key",
    "canonical_affine_terms", "carry_tile",
    "evidence_collection_key", "evidence_key",
    "pack_observed_cells", "pack_piece_observation", "parse_evidence_key",
    "parse_tile_key",
    "parse_window_key", "pool_key", "pose_collection_key", "pose_key",
    "region_evidence_collection_key", "region_pose_collection_key",
    "ring_masks", "tile_key",
    "unpack_observed_cells", "unpack_piece_halo", "window_key",
]

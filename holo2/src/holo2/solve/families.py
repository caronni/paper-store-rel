"""solve's record families, REGISTERED: the wall-side half of records.py.

Split out of ``records.py`` at H5 P1, when the calibration family's
collections hook took that module past the 1000-line cap — and the cap
named a real joint, not an arithmetic one: ``records.py`` declares WHAT
solve's records are (the frozen dataclasses and the tile-map algebra
they share), while THIS module declares how the commit wall must treat
them — the F-08 transition laws, the F-07 reference laws, the M4
collection memberships, the structural validators, and the one
composition-time binding (:func:`record_families`) that puts them all
under their kinds. The dependency runs one way, this module on
``records`` and never back, which is the same test the ``keys.py`` seam
passed at H4 W2.

Nothing here changed in the move: every law, every docstring and every
registration is the one ``records.py`` carried, and the package surface
still publishes ``record_families`` (``holo2.solve``), so the
composition root reads exactly what it always read.
"""
from __future__ import annotations

from dataclasses import replace

from ..core import (CertificateConflict, CommitRefusal, Record, RecordFamily,
                    ResourceKey, StateRegression, require_own_key)
from .contradiction import contradiction_family
from .keys import (KIND_CALIBRATION, KIND_EVIDENCE, KIND_POOL, KIND_POSE,
                   KIND_TILE, KIND_WINDOW, WINDOW_KEY_PARTS,
                   calibration_collection_key,
                   evidence_collection_key, parse_evidence_key,
                   parse_window_key, pose_collection_key,
                   region_evidence_collection_key,
                   region_pose_collection_key, tile_key)
from .lattice_seed import lattice_seed_family
from .records import (COLLECTION_CERTIFIED, CalibrationRecord,
                      EvidenceObservation, LabelPool, PoseRecord, TileRecord,
                      WindowRecord, WindowStatus, join_tiles)


def _tile_transition(key: ResourceKey, current: TileRecord,
                     proposed: TileRecord) -> None:
    """§11.3/L5: immutable certified content, monotone footing sets.

    Moved here from ``core.commit`` by R3; simplified at tile family v4,
    where the monotone-STATE half became constructively true. The rule is
    the tile map's, and core has no business knowing what a certificate
    is. A certified tile may still GAIN ``observed_by`` footings — done
    projection needs every committed observation of a certified key (§6)
    — and a proposal that dropped the mint is caught as the certified
    content moving, which is what it is.

    Since H4 W2 this rule ALSO serves as :func:`records.join_tiles`'s
    post-condition: the wall joins first and adjudicates the JOINED
    record, so what reaches here from a racing fire is never the raw
    proposal, and a correct join can never trip it. The audit is on the
    join's own code, which is where a lost mint or an edited certificate
    would now originate. It stays narrow — the TERMINAL half only —
    because that is the half whose loss is unrecoverable, and because
    the monotone sets are guaranteed by the join's construction rather
    than by a law that would also bind direct writers.
    """
    if not isinstance(current, TileRecord) or not current.certified:
        return
    if (proposed.minting != current.minting
            or proposed.bits_ref != current.bits_ref
            or proposed.metadata_bit != current.metadata_bit):
        raise CertificateConflict(
            f"{key}: certified content may not change (L5)")
    if not set(current.observed_by) <= set(proposed.observed_by):
        raise CertificateConflict(
            f"{key}: certified tile may not lose observing footings")
    if not set(current.baselined) <= set(proposed.baselined):
        raise CertificateConflict(
            f"{key}: certified tile may not lose baselined footings")


def _tile_collections(key: ResourceKey,
                      record: TileRecord) -> tuple[ResourceKey, ...]:
    if record.certified:
        return (COLLECTION_CERTIFIED,)
    return ()


def _window_transition(key: ResourceKey, current: WindowRecord,
                       proposed: WindowRecord) -> None:
    """F-08: RETIRED is terminal, and since v5 both statuses are outcomes.

    The glossary's law verbatim: windows end placed or retired(reason).
    ``ACTIVE`` is written by the fire that places the window and says so
    for the population's sake (the census and the observer read windows
    off these records); a retirement never un-happens and its reason
    never changes. Footing, region and extent are the KEY (identity law),
    so the geometry cannot move under a standing window at all.

    What this law no longer has to permit is the scheduling churn: with
    the staging states gone (v5), the only lawful move is ACTIVE ->
    RETIRED, and in practice even that does not happen — a placed window
    leaves the scheduling set.
    """
    if not isinstance(current, WindowRecord):
        return
    if current.status is WindowStatus.RETIRED and proposed != current:
        raise StateRegression(
            f"{key}: a retired window is terminal "
            f"({current.retired_reason!r}); refusing "
            f"{proposed.status.value!r}")


def _quarantine_only(current: Record, proposed: Record) -> bool:
    """Does this write move ONLY the quarantine marking, and only on?

    W5's declared transition, shared by the two families it touches
    because it is one rule: ``quarantined`` may go ``False -> True`` and
    nothing else may move. One-way is R6-Q16's terminality — a
    condemnation is never rehabilitated, and recovery is
    fresh-evidence-only (L8) — and "nothing else" is what keeps the F-08
    freezes below exactly as strict as they were about everything they
    were about.
    """
    return (getattr(current, "quarantined") is False
            and getattr(proposed, "quarantined") is True
            and replace(proposed, quarantined=False) == current)


def _pose_transition(key: ResourceKey, current: PoseRecord,
                     proposed: PoseRecord) -> None:
    """W5: a pose is IDENTITY plus one one-way marking (pose family v5).

    Through v4 this family declared no transition ON PURPOSE — window,
    page and affine ARE its key and the validator pinned its footing to
    the window's, so every field was identity and an overwrite with
    different content was unrepresentable (F-08 by construction). W5
    gives it its first non-identity field, so the law it used to get for
    free has to be WRITTEN: the quarantine marking may be set, once, and
    nothing else about a committed geometry may move under its name.

    Stated loudly rather than left implicit because that is what a
    declared transition IS — the freeze laws permit exactly this, and a
    family that quietly grew a mutable field would be the silent
    divergence R3 exists to prevent.
    """
    if not isinstance(current, PoseRecord) or proposed == current:
        return
    if not _quarantine_only(current, proposed):
        raise CommitRefusal(
            f"{key}: committed geometry is frozen; the only lawful move "
            "is the W5 quarantine marking, once, in one direction "
            f"(standing quarantined={current.quarantined})")


def _evidence_transition(key: ResourceKey, current: EvidenceObservation,
                         proposed: EvidenceObservation) -> None:
    """F-08: the durable payload atom is FROZEN under its name.

    The key names footing, tile and pose; the CONTENT — the LLR and
    observed-mask blobs and the calibration the piece was scored under —
    used to be silently replaceable, which is exactly the hole that
    breaks a certificate's provenance (the mint cites pieces by key; a
    swapped piece leaves the audit chain pointing at bytes that no
    longer exist). Pieces are deterministic functions of (raster, pose,
    calibration) (§9), so a lawful re-fire re-derives EQUAL content — a
    no-op — and a differing write means the derivation moved: refuse
    loudly (pre-freeze rule). When H5's calibration scopes land a
    re-score path, its semantics arrive as a DECLARED amendment to this
    law (replace-under-newer-calibration, or a re-keyed piece), never as
    a silent overwrite. (H5 P1 needed NO such amendment: the ctx
    correction applies at decode assembly, and no evidence is ever
    re-scored.)

    **W5 IS THAT AMENDMENT'S FIRST INSTANCE, and it is written here
    rather than assumed** (evidence family v4): a write that sets
    ``quarantined`` and moves NOTHING else is lawful, because a
    condemnation is a judgement ABOUT the piece and not a revision OF
    it — the LLRs, the observed mask and the calibration this piece was
    scored under are as frozen as they ever were. That is also ruling
    3's whole mechanism: this write is what bumps the key's version and
    kills an in-flight reader at the wall's existing staleness check.

    **F1 IS THE AMENDMENT'S SECOND INSTANCE** (2026-08-23, ruling J2-2;
    written here on review, where the first instance set the precedent).
    The DERIVATION of ``observed_ref`` moved: the sampler now packs the
    tile's cell mask AND its one-cell context halo, so the blob is 577
    bytes where it was 512, and the same (raster, pose, calibration) no
    longer re-derives the same bytes ACROSS the F1 line. No family
    version bumps, because the blob is SHAPE-VERSIONED BY LENGTH and
    leading-bit compatible: a 512-byte pre-F1 piece and a 577-byte F1
    piece are both lawful content under one key family, and every reader
    but ``records.unpack_piece_halo`` sees the identical first 4096 bits.
    The no-rewrite invariant this law states is not weakened, and what
    holds it is EXISTENCE, not the law: ``place_shared`` proposes a piece
    only where ``view.record(key) is None`` (``place_shared.py:817``), so
    a pre-F1 piece is never re-derived and never re-proposed. A resumed
    pre-F1 state can therefore hold both shapes on one tile, which the
    freeze handles by taking the whole component back to tile scope
    (``payload._freeze_with_owners``), never by mixing them.
    """
    if not isinstance(current, EvidenceObservation) or proposed == current:
        return
    if _quarantine_only(current, proposed):
        return                       # W5's declared quarantine transition
    moved = tuple(name for name in ("llr_ref", "observed_ref",
                                    "calibration_id", "quarantined")
                  if getattr(proposed, name) != getattr(current, name))
    raise CommitRefusal(
        f"{key}: evidence content is frozen (F-08); refusing a write that "
        f"moves {', '.join(moved) or 'nothing the key names'}")


def _calibration_transition(key: ResourceKey, current: CalibrationRecord,
                            proposed: CalibrationRecord) -> None:
    """F-08: a fit and its held-out verdict are FROZEN under their name.

    Scope, algorithm and the parameters' content address ARE the key, so
    a re-fit that changed anything is a DIFFERENT calibration at a
    different key — the only thing a write at the SAME key could alter is
    the held-out verdict (adopted / refused-with-reason), the shrinkage
    record, or the params ref's non-address fields, and none of those may
    move: committed evidence cites this record by name, and a verdict
    that flips under it is the adopt-or-refuse gate being out-voted after
    the fact.
    """
    if isinstance(current, CalibrationRecord) and proposed != current:
        raise CommitRefusal(
            f"{key}: a calibration and its held-out verdict are frozen "
            "(F-08); a different fit is a different key")


def _pool_transition(key: ResourceKey, current: LabelPool,
                     proposed: LabelPool) -> None:
    """F-08/§6.2: label pools only grow.

    The pool is the version mechanism for non-monotone fits — "versioned
    by label pools that only grow" — so the growth is the LAW, not an
    expectation: members are never dropped, a label kind never loses
    count, and a kind once present never disappears. The writer arrived
    at H5 P1 (``solve.calibration.CtxFitWorker``), whose pool record is
    the monotone high-water mark of what has EVER contributed — the live
    label population is derived at fire time with the quarantine filter,
    so a condemnation shrinks the fit's input and never this record.
    """
    if not isinstance(current, LabelPool):
        return
    if not set(current.member_window_ids) <= set(proposed.member_window_ids):
        raise CommitRefusal(
            f"{key}: a label pool only grows (§6.2); refusing a write that "
            "drops member windows")
    counts = dict(proposed.label_site_count_by_kind)
    shrunk = tuple(
        kind for kind, count in current.label_site_count_by_kind
        if counts.get(kind, -1) < count)
    if shrunk:
        raise CommitRefusal(
            f"{key}: a label pool only grows (§6.2); refusing a write that "
            f"shrinks label counts for {', '.join(shrunk)}")


# --------------------------------------------------------------------------
# F-07's relational half: what each family STANDS ON
# --------------------------------------------------------------------------
# Declarations, not lookups (``registry.RecordFamily.references``): the
# wall resolves each against the decided batch plus the store. Every one
# is LAW on the live path — a placement fire writes the window, the pose,
# the fit and the pieces in ONE batch — so batch inclusion or the store
# satisfies them all. Families that declare NOTHING say why at their
# registration.


def _tile_references(key: ResourceKey,
                     record: TileRecord) -> tuple[ResourceKey, ...]:
    """A certified tile stands on the poses its mint names (M10, L5).

    Its provenance is all a later audit has, and a contradiction would
    otherwise find no placement to quarantine. Below a certificate there
    is nothing to declare: footing ids are not keys."""
    if record.minting is None:
        return ()
    return (record.minting.pose_id, *record.minting.contributors)


def _pose_references(key: ResourceKey,
                     record: PoseRecord) -> tuple[ResourceKey, ...]:
    """Committed geometry stands on the window whose working set it fits."""
    return (record.window_id,)


def _window_references(key: ResourceKey,
                       record: WindowRecord) -> tuple[ResourceKey, ...]:
    """A window stands on the surveyed region it is a working set OF."""
    return (record.region_id,)


def _evidence_references(key: ResourceKey,
                         record: EvidenceObservation) -> tuple[ResourceKey, ...]:
    """The payload atom stands on its pose AND its calibration — the
    provenance a certificate inherits: WHERE the cells were read, and
    what turned scores into bounded LLRs (L2)."""
    return (record.pose_id, record.calibration_id)


def _calibration_references(key: ResourceKey,
                            record: CalibrationRecord) -> tuple[ResourceKey, ...]:
    """A fit stands on what it is a fit OVER (a window; §5.4 a pool)."""
    return (record.scope,)


def _calibration_collections(key: ResourceKey,
                             record: CalibrationRecord
                             ) -> tuple[ResourceKey, ...]:
    """An ADOPTED pool fit joins its pool's calibration collection.

    H5's subscription key (``keys.calibration_collection_key``): the one
    region-scoped resource a payload decode names beside its own tile's
    evidence, VERSIONED ON ADOPTION ONLY — a refused fit joins nothing
    and wakes nobody, a pool write bumps the pool's own key and not this,
    and the per-window ``pava-v1`` fits (scope kind ``window``) never
    enter it. Membership is a pure function of (key, record), so the
    resource table can derive it at commit and in full at rebuild.
    """
    if record.scope.kind == KIND_POOL and record.heldout.adopted:
        return (calibration_collection_key(record.scope),)
    return ()


def _validate_evidence(key: ResourceKey,
                       record: EvidenceObservation) -> None:
    parse_evidence_key(key)
    require_own_key(key, record)


def _validate_pose(key: ResourceKey, record: PoseRecord) -> None:
    """Its own key, and the footing its window names (§5.4, L2)."""
    require_own_key(key, record)
    footing_id, _region, _extent = parse_window_key(record.window_id)
    if footing_id != record.footing_id:
        raise ValueError(
            f"pose names footing {record.footing_id}, its window "
            f"{footing_id}")


def _evidence_collections(key: ResourceKey,
                          record: EvidenceObservation) -> tuple[ResourceKey, ...]:
    """A piece joins its WORK KEY's collection and its (footing, region)'s.

    From the KEY, not the record: the resource table indexes keys, and
    the collection a piece joins has to be the one a worker named when
    it subscribed to "the evidence on this work key". Validation has
    already proven the key is this record's own.

    The second is the F2a review fix (2026-08-23,
    ``keys.region_evidence_collection_key``): the region ctx fit's
    population is PIECES, and until it could name them a commit that
    added pieces without adding a pose — the re-read, and nothing else
    in the tree writes evidence — moved nothing the fit read, so v1's
    "replay the affected region's coupled fit" never happened. An
    ordinary placement commits its pose and its pieces in one batch, so
    on that path this collection bumps where the pose collection already
    bumped and buys no second wake.
    """
    _footing, page, ty, tx, stream, pose = parse_evidence_key(key)
    footing_id, region, _extent = parse_window_key(
        ResourceKey(KIND_WINDOW, pose.parts[:WINDOW_KEY_PARTS]))
    return (evidence_collection_key(tile_key(page, ty, tx, stream)),
            region_evidence_collection_key(footing_id, region))


def _pose_collections(key: ResourceKey,
                      record: PoseRecord) -> tuple[ResourceKey, ...]:
    """A pose joins its window's collection AND its (footing, region)'s.

    The second is H5's (``keys.region_pose_collection_key``): the region
    ctx fit's label pool is fed by the committed placements of one footing
    in one region, and per-window keys cannot say "a member arrived" for a
    window the fit never enumerated (a subdivision child's, say). Derived
    only — a hook is a law at the wall and moves no byte of the wire, so
    no family bump.
    """
    _footing, region, _extent = parse_window_key(record.window_id)
    return (pose_collection_key(record.window_id),
            region_pose_collection_key(record.footing_id, region))


def _pose_validator(page_domain: tuple[int, ...]):
    """The pose's own checks, plus the session's declared page domain."""
    allowed = frozenset(page_domain)

    def validate(key: ResourceKey, record: PoseRecord) -> None:
        _validate_pose(key, record)
        if allowed and record.page not in allowed:
            raise ValueError(
                f"page {record.page} is outside the session's declared page "
                f"domain {tuple(sorted(allowed))} (§5.1)")

    return validate


def record_families(page_domain: tuple[int, ...] = ()
                    ) -> tuple[RecordFamily, ...]:
    """solve's families, bound to one session's declared page domain.

    solve is the one package whose schema has a composition-time
    parameter: "a pose addresses a page in THIS session's domain" is a
    structural property of a record, but the domain itself is named by the
    lineage (§5.1). An empty domain registers no page gate, which is what
    a unit test that never declares one wants.

    The HINT family is gone (H4 W2's clean-slate sweep): a hint was a
    scheduling annotation promoted to a record, and the pull model asks
    the committed poses at fire time instead. Its kind is unregistered,
    so a pre-sweep state holding one refuses at open — R3-lawful and the
    pre-freeze rule working as designed (DESIGN §8).
    """
    return (
        # The ONE commutative family (H4 W2, ruling 1). It declares BOTH
        # ``merge`` and ``transition``, and the registry states the
        # composition: the wall joins first and then adjudicates the
        # JOINED record, so ``_tile_transition`` stopped being the law a
        # racing proposal trips over and became the post-condition that
        # audits the join. On a correct merge it can never fire — which
        # is exactly why it is worth keeping, and what the
        # fault-injection in ``tests/core/test_merge.py`` shows.
        # No family-version bump: a hook is a LAW at the wall and moves
        # no byte of the wire, so every state written before it stays
        # readable and stays lawful.
        RecordFamily(TileRecord, KIND_TILE, version=4, structural=True,
                     transition=_tile_transition,
                     merge=join_tiles,
                     collections=_tile_collections,
                     references=_tile_references),
        # v5 (H4 W5): the pose gained ONE non-identity field — the
        # quarantine marking — so the law it used to get for free from
        # "every field is identity" is now DECLARED (_pose_transition).
        # The WIRE moved, so a pre-W5 state refuses at open by manifest,
        # which is the pre-freeze rule working as designed (DESIGN §8).
        RecordFamily(PoseRecord, KIND_POSE, version=5, structural=True,
                     validate=_pose_validator(page_domain),
                     transition=_pose_transition,
                     collections=_pose_collections,
                     references=_pose_references),
        # v5 (H4 W2, the pull model): the status vocabulary lost its two
        # scheduling values, so the WIRE moved — a state written before
        # this build can hold a ``"sleeping"`` a v5 reader has no meaning
        # for, and refusing it by manifest is the pre-freeze rule working
        # exactly as designed (DESIGN §8).
        RecordFamily(WindowRecord, KIND_WINDOW, version=5, structural=True,
                     validate=require_own_key,
                     transition=_window_transition,
                     references=_window_references),
        # v4 (H4 W5): the quarantine marking, and the declared amendment
        # to the F-08 freeze that lets it move once. Wire change, same
        # loud refusal story as the pose above.
        RecordFamily(EvidenceObservation, KIND_EVIDENCE, version=4,
                     validate=_validate_evidence,
                     transition=_evidence_transition,
                     collections=_evidence_collections,
                     references=_evidence_references),
        # F-07: the pool id IS the key, and the grow-only law above is
        # stated per NAME — a pool filed under another scope's id would
        # be compared against the wrong membership.
        # A pool DECLARES NO REFERENCES either, as a ruling rather than
        # an omission (upheld by H5 P1, the round that built the writer):
        # its members are window KEYS, and a member window is a PLAN long
        # before it is a record — a pool may legitimately grow a window
        # the fit derived from a committed pose whose WindowRecord landed
        # in the same batch, but "the members are committed windows" as a
        # BATCH-SHAPE law would also forbid the high-water-mark merge a
        # later resume replays. The writers keep the discipline; the wall
        # does not re-state it.
        RecordFamily(LabelPool, KIND_POOL, version=1,
                     validate=require_own_key,
                     transition=_pool_transition),
        # H5 P1: the family gained its ``collections`` hook (adopted
        # pool fits join the pool's calibration collection). A hook is a
        # law at the wall and moves no byte of the wire — no bump.
        RecordFamily(CalibrationRecord, KIND_CALIBRATION, version=2,
                     validate=require_own_key,
                     transition=_calibration_transition,
                     collections=_calibration_collections,
                     references=_calibration_references),
        lattice_seed_family(),          # R5, ``solve/lattice_seed.py``
        # W5's ONE new family, declared in ``solve/contradiction.py``
        # for the same reason R5's is declared in its own file: the fact
        # depends on core and on the key vocabulary, never on a record.
        contradiction_family(),
    )


__all__ = ["record_families"]

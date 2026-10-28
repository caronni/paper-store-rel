"""W5's consumer: what a contradiction condemns, and who asks.

``words.known_position_words`` is the RECONCILIATION half of ruling 2;
this file is the CONSUMER half it had to be carried with. v1 feeds its
reduced words into ``promoted_continuation_hints``
(``receive/place.py:1693``) — "remove every continuation proposal owned
by a quarantined placement" — and into the durable
``AddressArtifact.bch_conflicts`` whose contributors the session then
refuses payload evidence from (``session.py:442-446``).

holo2's pull model has no hints to revoke, so the SAME consumer is
spelled where the steers are computed now:

* ``place_job.consult`` never offers a quarantined pose,
* ``payload.route_evidence_keys`` never decodes a quarantined
  piece,

and both ask :func:`is_quarantined`. One predicate, two readers, one
marking — because "never offered" and "never decoded" must not be able
to drift apart.

THE THREE RULINGS THIS FILE IS (user, 2026-08-18)
-------------------------------------------------
**1. DONE IS INVIOLABLE.** Quarantine's entire jurisdiction is
UNCERTIFIED material. A contradicted position whose tile is CERTIFIED is
not quarantine's case at all — the certificate vindicates the geometry
that read it ("if payload is decoded, we know with much higher
probability the correct address"), and a genuine conflict there belongs
to the fatal layer. :func:`contradiction_writes` skips it outright. And
``tilemap.project_done`` is UNAMENDED — it does not know this module
exists — so a quarantine write moves exactly ZERO done pixels and the
F-23 cache key (committed poses x certified keys) stands as ruling 1
says it does. That is a property of the code, not a promise about it:
``tests/solve/test_quarantine.py`` projects a region before and after a
condemnation and compares the arrays.

**3. STALENESS VIA QUARANTINE DATA.** The condemnation IS a write on
the condemned keys — a declared F-08 transition flipping ``quarantined``
on the pose and on each of its evidence pieces — so it bumps their
versions, and every in-flight worker whose read-set names one dies at
the wall's EXISTING staleness check (``CommitEngine.is_current``). A
payload attempt names the pieces it reads (§7, PROVIDERS PY2), which is
exactly the race ruling 3 closes: a decode running over evidence that is
condemned mid-flight cannot land. No new mechanism, one write pattern.

**5. TERMINALITY, BOTH SIDES, NO VOTING** (R6-Q16). Neither side is
preferred. The DECODED side — the placement whose reads formed the
contradicting word — is committed as a pose BORN QUARANTINED: retained
as a record so the fact's contributor set names something real, never
offered by a consult, and emitting no evidence at all, so there is
nothing of its to exclude later. The GEOMETRY side — every committed
pose already asserting that position at this footing — is marked
quarantined together with all of its evidence. Never rehabilitated: the
transition is one-way and recovery is fresh-evidence-only (L8).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from ..core import FootingId, Record, ResourceKey, StreamId, Write
from . import pose_audit
from .contradiction import WordContradiction
from .keys import parse_evidence_key, tile_key
from .place_model import KnownWord
from .pose_fit import SegmentSample
from .records import EvidenceObservation, PoseRecord
from .reference import ReferenceFieldProvider
from .view import PlaneView
from .words import known_position_words

#: The emission's W5 outcome: this placement's own words contradicted
#: the geometry that put it here, so it emits nothing and condemns both
#: sides instead. Spelled once because ``place_shared`` returns it and
#: ``place_job`` reads it to retire the window.
OUTCOME_CONTRADICTION = "word_contradiction"


def is_quarantined(record: Record | None) -> bool:
    """Is this pose or evidence piece condemned? (ruling 2's consumer.)"""
    return isinstance(record, (PoseRecord, EvidenceObservation)) and bool(
        record.quarantined)


@dataclass(frozen=True)
class Contradicted:
    """What a fire found: the facts, and the writes that condemn them."""

    facts: tuple[WordContradiction, ...] = ()
    writes: tuple[Write, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.facts)


def evidence_of_pose(view: PlaneView,
                     pose_id: ResourceKey) -> tuple[ResourceKey, ...]:
    """Every committed evidence key whose pose is this one.

    A pose does not index its pieces — the arrow runs the other way by
    design (a piece NAMES its pose, §5.4) — so this is one pass over the
    evidence index. It runs only on a contradiction, which L8 expects to
    be silent (1,780 known-position reads on record, 0 conflicts
    measured), so the scan is paid at most once per condemned placement
    and never on the quiet path.
    """
    return tuple(sorted(
        key for key in view.index().evidence_footings
        if parse_evidence_key(key)[5] == pose_id))


def quarantine_writes(view: PlaneView,
                      pose_id: ResourceKey) -> tuple[Write, ...]:
    """Mark one standing pose and ALL its evidence quarantined.

    THE WHOLE PLACEMENT, not the contradicted tile alone: v1 condemns
    the PATCH (``model.py:592-598``) and refuses every payload block
    whose ORIGIN is one of them, so a placement that lied about one
    position is not trusted about the others.

    These writes ARE ruling 3's staleness mechanism (see the module
    docstring). Idempotent by construction: a pose already quarantined
    proposes nothing, so a second contradiction naming it writes no
    second time and wakes nobody.
    """
    pose = view.record(pose_id)
    if not isinstance(pose, PoseRecord) or pose.quarantined:
        return ()
    writes: list[Write] = [Write(pose_id, replace(pose, quarantined=True))]
    for key in evidence_of_pose(view, pose_id):
        piece = view.record(key)
        if isinstance(piece, EvidenceObservation) and not piece.quarantined:
            writes.append(Write(key, replace(piece, quarantined=True)))
    return tuple(writes)


def _geometry_side(view: PlaneView, tile: ResourceKey,
                   footing_id: FootingId) -> tuple[ResourceKey, ...]:
    """The poses that already assert this position AT THIS FOOTING.

    Ruling 4's scope, read off the evidence index: a piece names one
    footing and one pose, and holding a piece on this tile IS the claim
    that this tile sits under that pose. Other footings are never
    compared — the certificate layer is the only cross-scope arbiter,
    and it is fatal.
    """
    footings = view.index().evidence_footings
    return tuple(sorted({
        parse_evidence_key(key)[5] for key in view.evidence_on(tile)
        if footings.get(key) == footing_id}))


def contradiction_writes(view: PlaneView, *, footing_id: FootingId,
                         stream: StreamId, pose_id: ResourceKey,
                         words: tuple[KnownWord, ...]) -> Contradicted:
    """The W5 verdict over one fire's reduced words (rulings 1, 4, 5).

    ``pose_id`` is the DECODED side — the placement this fire is about
    to commit, whose reads formed the words. It is PASSED rather than
    looked up because at this moment it is not a record yet: a
    contradicting fire commits it born-quarantined in the same batch as
    the fact that names it, and the wall's reference check resolves the
    two against each other.

    A word that is not a ``conflict`` is not this function's business —
    v1's "failures never veto placement": a word that did not decode is
    silence, and one that decoded to its own counter is a PASS. A
    conflict on a CERTIFIED tile is not either (ruling 1).
    """
    facts: list[WordContradiction] = []
    writes: list[Write] = []
    for word in words:
        if not word.conflict:
            continue
        assert word.decoded_counter is not None and word.errors is not None
        ty, tx = word.tile_yx
        tile = tile_key(word.page, ty, tx, stream)
        standing = view.tile(tile)
        if standing is not None and standing.certified:
            continue                       # ruling 1: certified is vindicated
        fact = WordContradiction(
            footing_id=footing_id, page=word.page, ty=ty, tx=tx,
            expected_counter=word.expected_counter,
            decoded_counter=int(word.decoded_counter),
            errors=int(word.errors), erasures=int(word.erasures),
            decoded_contributors=tuple(sorted(set(word.contributors)
                                              | {pose_id})),
            geometry_contributors=_geometry_side(view, tile, footing_id))
        facts.append(fact)
        writes.append(Write(fact.resource_key(), fact))
        for condemned in fact.geometry_contributors:
            writes.extend(quarantine_writes(view, condemned))
    return Contradicted(tuple(facts), tuple(writes))


def word_verdict(view: PlaneView, *, pose: PoseRecord,
                 provider: ReferenceFieldProvider, stream: StreamId,
                 capture_id: str, sample: SegmentSample | None,
                 observed: np.ndarray, page: int,
                 page_origin_yx: tuple[int, int],
                 rot_k: int) -> Contradicted:
    """Harvest, reduce, adjudicate — W5's three steps, in one call.

    The emission block's one line into this wave, and the only place
    the three carried halves meet: the HARVEST is v1's
    (``pose_audit.observations_for_segment`` — the authoritative pilot
    reads under the audited core — stamped with the pose that made
    them), the REDUCE is v1's (``words.known_position_words``), and the
    verdict is :func:`contradiction_writes`.

    It takes the placement's parts rather than the placement, so this
    module never imports ``place_shared`` — which imports this one.

    A placement carrying no sample (a test double) reduces nothing and
    contradicts nothing. So does every healthy window: L8 records 1,780
    known-position reads and ZERO conflicts, which is what makes the
    quiet path the empty verdict by design.
    """
    if sample is None:
        return Contradicted()
    pose_id = pose.resource_key()
    observations = pose_audit.observations_for_segment(
        sample, observed, provider, page, page_origin_yx, rot_k,
        capture_id=capture_id, family_seed=provider.spec.family_seed,
        pose_id=pose_id)
    return contradiction_writes(
        view, footing_id=pose.footing_id, stream=stream, pose_id=pose_id,
        words=known_position_words(observations, provider.spec))


__all__ = [
    "Contradicted", "OUTCOME_CONTRADICTION", "contradiction_writes",
    "evidence_of_pose", "is_quarantined", "quarantine_writes",
    "word_verdict",
]

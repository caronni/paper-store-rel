"""W5's missing layer: the ADDRESS-WORD contradiction, as a durable fact.

DESIGN L8 and H4-W5-PLAN. The receiver reconciles three layers, and two
of them already had a rule: payload SOFT sums (distinct captures, one
ppc), payload HARD corroborates at the wall and a disagreement is FATAL
(L5, never voted). The missing row is ADDRESS WORDS — decision-level
reconciliation with CONTAINMENT rather than fatality, because the layer
below it sums lawfully and the layer above it already owns the fatal
case.

This module owns the FACT. Its consumer — what a contradiction
condemns, and the predicate three readers ask — is ``quarantine.py``,
which is a separate file for the ordinary reason: a family declaration
may not depend on the records it is registered beside (``records``
imports THIS module, exactly as it imports ``lattice_seed``).

The fact is v1's ``BchConflictRecord`` (``receive/types.py:697-734``)
as a holo2 record: keyed on the CONTRADICTED POSITION and carrying BOTH
sides' full contributor sets in
:class:`~holo2.solve.records.MintRef`'s own contributor shape (sorted,
unique pose keys — that class exists for exactly "the primary witness
is the whole set").
"""
from __future__ import annotations

from dataclasses import dataclass

from ..core import (CommitRefusal, FootingId, KeyField, KeySpec, RecordFamily,
                    ResourceKey, build_key, require_own_key,
                    require_sorted_unique)
from .keys import KIND_POSE

KIND_CONTRADICTION = "contradiction"

#: The subject is the CONTRADICTED WORD POSITION at one footing — ruling
#: 4's (capture, footing) scope made structural: two footings that
#: disagree about one printed tile hold two facts, and nothing in this
#: wave ever compares them. v1 keys its quarantine namespace the same
#: way, per (capture, evidence lane).
CONTRADICTION_SPEC = KeySpec(KIND_CONTRADICTION, (
    KeyField("footing_id"), KeyField("page", cast=int),
    KeyField("ty", cast=int), KeyField("tx", cast=int)))


def contradiction_key(footing_id: FootingId, page: int, ty: int,
                      tx: int) -> ResourceKey:
    """The contradicted word position at one footing (ruling 4's scope)."""
    return build_key(CONTRADICTION_SPEC, footing_id=footing_id, page=page,
                     ty=ty, tx=tx)


@dataclass(frozen=True)
class WordContradiction:
    """One known-position word that named a tile its geometry did not.

    ``expected_counter`` is what the placements at this position claim
    the format prints here; ``decoded_counter`` is what the ink said,
    through a decode that was LEGAL — inside the BCH radius, five known
    zero pads clean — which is what makes this a contradiction rather
    than a read failure. ``errors`` and ``erasures`` are the decode's
    own audit, carried from v1's ``BchConflictRecord``.

    THE TWO CONTRIBUTOR SETS are the fact's point, and both are
    ``MintRef.contributors``' shape (sorted, unique pose keys):

    * ``decoded_contributors`` — the placements whose reads were
      SELECTED into the vote that produced ``decoded_counter`` (v1's
      ``contributor_patch_ids``), plus the placement that ran the
      reduce;
    * ``geometry_contributors`` — the placements that already assert
      this position at this footing, i.e. hold committed evidence on
      the tile the position names.

    Both are condemned IDENTICALLY and neither is voted on (R6-Q16). A
    set may be empty on one side — a first placement contradicting
    nothing standing has no geometry side — but never on both, because
    a contradiction nobody contributed to is not a fact about anything.

    IMMUTABILITY, and why the family declares it FROZEN: the fact is
    COMPLETE AT MINT. Both sides are known at reduce time — the decode
    and the standing evidence are read in one fire — so there is no
    later state for it to move to, and a write that revised it would be
    out-voting the containment after the fact. That is the same law
    evidence and calibration carry (F-08), for the same reason.
    """

    footing_id: FootingId
    page: int
    ty: int
    tx: int
    expected_counter: int
    decoded_counter: int
    errors: int
    erasures: int
    decoded_contributors: tuple[ResourceKey, ...] = ()
    geometry_contributors: tuple[ResourceKey, ...] = ()

    def __post_init__(self) -> None:
        if self.decoded_counter == self.expected_counter:
            raise ValueError(
                "a WordContradiction's decoded counter must DIFFER from the "
                f"expected one (both {self.expected_counter})")
        if self.errors < 0 or self.erasures < 0:
            raise ValueError(
                "WordContradiction errors/erasures are decode counts")
        require_sorted_unique(self.decoded_contributors,
                              "WordContradiction.decoded_contributors")
        require_sorted_unique(self.geometry_contributors,
                              "WordContradiction.geometry_contributors")
        if not self.decoded_contributors and not self.geometry_contributors:
            raise ValueError(
                "a WordContradiction names no contributor on either side; "
                "a contradiction nobody contributed to is not a fact")
        for key in self.decoded_contributors + self.geometry_contributors:
            if key.kind != KIND_POSE:
                raise ValueError(
                    f"WordContradiction contributors are pose keys, got {key}")

    def resource_key(self) -> ResourceKey:
        return contradiction_key(self.footing_id, self.page, self.ty, self.tx)

    def condemned(self) -> tuple[ResourceKey, ...]:
        """Both sides, identically: every pose this fact quarantines."""
        return tuple(sorted(set(self.decoded_contributors)
                            | set(self.geometry_contributors)))


def _contradiction_transition(key: ResourceKey, current: WordContradiction,
                              proposed: WordContradiction) -> None:
    """F-08: a contradiction is FROZEN under its position.

    Complete at mint (above), so the only write a second fire can make
    here is an EQUAL one — same position, same legal decode, same two
    sides — and the wall drops an equal write before this hook is
    reached. Anything else says a later reader revised a containment
    decision, which is the one thing terminality forbids.
    """
    if isinstance(current, WordContradiction) and proposed != current:
        raise CommitRefusal(
            f"{key}: a word contradiction is frozen (F-08, R6-Q16 "
            "terminality); refusing a write that revises it")


def _contradiction_references(key: ResourceKey, record: WordContradiction,
                              ) -> tuple[ResourceKey, ...]:
    """The fact stands on BOTH sides' poses (F-07).

    A quarantine whose contributors nobody committed would condemn
    nothing and audit nothing — ``_tile_references``' argument for a
    certificate's mint, in the mirror. It is also what makes the
    born-quarantined decoded side lawful in ONE batch: the fire writes
    the pose and the fact together, and the wall resolves the reference
    against the decided batch.
    """
    return record.condemned()


def contradiction_family() -> RecordFamily:
    """W5's ONE new family, as ``families.record_families`` registers it."""
    return RecordFamily(WordContradiction, KIND_CONTRADICTION, version=1,
                        structural=True, validate=require_own_key,
                        transition=_contradiction_transition,
                        references=_contradiction_references)


__all__ = [
    "CONTRADICTION_SPEC", "KIND_CONTRADICTION", "WordContradiction",
    "contradiction_family", "contradiction_key",
]

"""The record registry: how core stores facts it does not know the shape of.

R3's mechanism. Before it, ``core/records.py`` held every durable record
in the tree and ``codec``/``store``/``commit``/``resources`` dispatched on
a hard-coded table — so a printed-format schema change was core surgery,
and core knew what a tile, a pose and a survey region are. It should not:
core is the algorithm-free machine.

A **record family** is one durable record type plus the rules core needs
to store it generically:

* ``kind`` — the ``ResourceKey`` kind its records live under (``None``
  for the session-identity family, which is the envelope header and has
  no key);
* ``version`` — the family's schema version. The registry's **manifest**
  (every family name and version, sorted) is the store's schema identity:
  a state whose manifest differs from the build's is refused at open,
  naming the families that moved. That is the whole pre-freeze migration
  policy (DESIGN §10.4) made local — a subsystem changes its own record
  and bumps its own version, and no other package's code moves;
* ``validate`` — a structural validator run on every proposed write and
  on every record read back from an envelope, **given the key the record
  is stored under**. Key-aware because a record whose own identity
  disagrees with its key is an illegal durable state, and because the key
  parsing a family's ``collections`` callback does is fallible: under the
  publication-order law (DESIGN §6) that parse has to happen here, before
  anything moves, rather than after the store is durable. Structural: it
  may look at the key, at the record, and at composition-time constants
  the owning package closed over (a declared page domain, say), never at
  other records;
* ``transition`` — the monotone/immutability rule between the record
  standing at a key and the one proposed for it. This is where the tile
  map's "CERTIFIED is terminal" law lives now: the rule is unchanged, it
  simply stopped being something ``core.commit`` knows by name;
* ``merge`` — the fourth hook (H4 W2, the commutative-merge ruling): a
  family whose algebra is a JOIN declares it, and the wall applies it
  against the record it currently holds instead of asking a compare-and-
  swap whether the proposal is still fresh. Signature ``(key, current,
  proposed) -> merged``.

  **The proposed record IS the operation input.** For a join semilattice
  that is not a shortcut, it is the definition: the fire computes its
  carry against the snapshot it read (``solve.records.carry_tile``), so
  its proposal is already ``snapshot ⊔ gain``; re-applying the OPERATION
  against what stands now is ``current ⊔ proposal``, which is the same
  value whatever the snapshot was, because ⊔ is idempotent, commutative
  and associative and ``snapshot ⊑ current``. Nothing extra rides across
  the wall — no delta encoding, no "what I gained" side channel — and a
  serial run is unchanged BY CONSTRUCTION: there ``current`` IS the
  snapshot, so ``current ⊔ proposal == proposal`` and the batch commits
  byte-for-byte as it was proposed.

  **Composition with ``transition``, stated because a family may declare
  both.** The tile family does, and the order is: MERGE FIRST, then the
  family's ordinary adjudication — validator and transition rule — runs
  on the MERGED record, exactly as it would on any proposal. So the
  transition law is not bypassed by the merge; it becomes the merge's
  POST-CONDITION, the one auditor that catches a join implementation
  that lost a monotone member or edited terminal content. On a correct
  merge it can never fire, which is what a post-condition is for. A
  family that declares only ``merge`` is lawful (nothing audits it); a
  family that declares only ``transition`` is the compare-and-swap
  default every other family keeps.

  What the merge may NOT do is resolve a contradiction: the tile map's
  "two different certified contents for one tile" is raised INSIDE the
  merge, as the same ``CertificateConflict`` the transition raises today
  (F-11's lawful data event), because a join that cannot join is not a
  scheduling accident;
* ``references`` — the record keys this record STANDS ON (F-07's
  relational half). A pure declaration: given the key and the record, it
  names the keys that must already BE facts. The wall checks them against
  the batch it is deciding plus the store, and refuses a write that names
  a record nobody committed.

  Why this cannot ride ``validate``: a validator may look at the key, at
  the record and at composition-time constants, and at **nothing else** —
  that is its contract, stated above, and it is what lets one validator
  run at the commit wall and at load without the store being consulted
  twice for two different answers. Existence is not a property of a
  record; it is a property of the state a record is joining. So the
  question is asked once, at the one place that holds both the decided
  batch and the store: the adjudication pass in ``core.commit``.

  Why one check is complete for all time: facts are immutable and are
  never deleted (F-08, and the store is append-only), so a reference that
  resolves at commit resolves forever. There is no re-check, no repair
  pass, and no background audit — the wall is the whole mechanism.

  A dangling reference is a **wrong writer**, not a data event: it means
  the code that built the batch left out the record it cites. It refuses
  as an ordinary ``CommitRefusal`` (fatal, F-11's other half), never as a
  ``CertificateConflict``, and so it never takes the terminal-fact path;
* ``collections`` — the membership resources one fact joins (M4), so the
  resource table can maintain collection versions without knowing which
  kinds have collections;
* ``structural`` — does a write of this family expand the work frontier?
  The orchestrator re-enumerates providers when one lands. Scheduling
  reads this instead of listing domain kinds it should not know.

Composition is explicit: each package publishes ``RECORD_FAMILIES`` and
the composition root (``cli``; a test composes what it needs) builds one
``RecordRegistry`` from them. Nothing registers itself on import — there
are no cross-package globals in this tree.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

from .keys import Record, ResourceKey


class RegistryError(ValueError):
    """A record registry was composed wrongly, or asked about a stranger."""


class UnknownRecordError(RegistryError):
    """A record type (or envelope type tag) no registered family declares."""


@dataclass(frozen=True)
class RecordFamily:
    """One durable record type and the rules core stores it by.

    ``name`` is the record type's own name, which is the tag the envelope
    carries — a rename is therefore a manifest change and refuses old
    states loudly, which is exactly the pre-freeze rule.
    """

    record_type: type
    kind: str | None
    version: int = 1
    structural: bool = False
    validate: Callable[[ResourceKey, Any], None] | None = None
    transition: Callable[[ResourceKey, Any, Any], None] | None = None
    merge: Callable[[ResourceKey, Any, Any], Any] | None = None
    collections: Callable[[ResourceKey, Any], tuple[ResourceKey, ...]] | None = None
    references: Callable[[ResourceKey, Any], tuple[ResourceKey, ...]] | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise RegistryError(
                f"{self.name}: family version must be >= 1, got {self.version}")
        if self.kind is not None and not self.kind:
            raise RegistryError(f"{self.name}: kind must be non-empty or None")
        if self.kind is None and self.merge is not None:
            raise RegistryError(
                f"{self.name}: the session identity is not stored at a key, "
                "so nothing could ever hold a record to merge against")

    @property
    def name(self) -> str:
        return self.record_type.__name__


class RecordRegistry:
    """The composed record vocabulary of one build.

    Refuses at composition time what would otherwise be discovered at a
    read: two families under one name, two families under one key kind,
    the same record type declared twice, or a set with no (or more than
    one) session-identity family.
    """

    def __init__(self, families: Iterable[RecordFamily]) -> None:
        by_name: dict[str, RecordFamily] = {}
        by_type: dict[type, RecordFamily] = {}
        by_kind: dict[str, RecordFamily] = {}
        session: RecordFamily | None = None
        for family in families:
            if family.name in by_name:
                raise RegistryError(
                    f"{family.name}: registered twice (families are named by "
                    "their record type)")
            if family.record_type in by_type:
                raise RegistryError(
                    f"{family.record_type!r}: registered under two names")
            by_name[family.name] = family
            by_type[family.record_type] = family
            if family.kind is None:
                if session is not None:
                    raise RegistryError(
                        f"{session.name} and {family.name} both claim to be "
                        "the session identity (kind=None)")
                session = family
                continue
            if family.kind in by_kind:
                raise RegistryError(
                    f"key kind {family.kind!r}: claimed by both "
                    f"{by_kind[family.kind].name} and {family.name}")
            by_kind[family.kind] = family
        if session is None:
            raise RegistryError(
                "no session-identity family (exactly one family must declare "
                "kind=None); a store cannot name its lineage without one")
        self._by_name = by_name
        self._by_type = by_type
        self._by_kind = by_kind
        self._session = session
        self._manifest = tuple(sorted(
            (family.name, family.version) for family in by_name.values()))
        self._structural_kinds = frozenset(
            family.kind for family in by_name.values()
            if family.structural and family.kind is not None)
        #: Kinds whose family declared a commutative merge. The engine's
        #: staleness test projects them OUT of an attempt identity — a
        #: key the wall joins is a key no proposal can be stale about.
        self._merge_kinds = frozenset(
            family.kind for family in by_name.values()
            if family.merge is not None and family.kind is not None)

    # -- identity ----------------------------------------------------------

    def manifest(self) -> tuple[tuple[str, int], ...]:
        """The store's schema identity: (family name, version), sorted."""
        return self._manifest

    def manifest_json(self) -> list[list[Any]]:
        return [[name, version] for name, version in self._manifest]

    @property
    def session_family(self) -> RecordFamily:
        """The envelope-header family (the one with no key kind)."""
        return self._session

    @property
    def session_type(self) -> type:
        return self._session.record_type

    def families(self) -> tuple[RecordFamily, ...]:
        return tuple(self._by_name[name] for name in sorted(self._by_name))

    def structural_kinds(self) -> frozenset[str]:
        """Kinds whose arrival may expand the work frontier (§9 refresh)."""
        return self._structural_kinds

    def merge_kinds(self) -> frozenset[str]:
        """Kinds the wall JOINS instead of version-validating (H4 W2)."""
        return self._merge_kinds

    # -- lookup ------------------------------------------------------------

    def family_of(self, record: Record) -> RecordFamily:
        family = self._by_type.get(type(record))
        if family is None:
            raise UnknownRecordError(
                f"{type(record).__name__} is not a registered holo2 record")
        return family

    def family_named(self, name: str) -> RecordFamily | None:
        return self._by_name.get(name)

    def kind_of(self, record: Record) -> str:
        """The key kind a record of this type must be stored under."""
        kind = self.family_of(record).kind
        if kind is None:
            raise UnknownRecordError(
                f"{type(record).__name__} is the session identity; it is not "
                "stored at a key")
        return kind

    # -- the rules core applies --------------------------------------------

    def validate(self, key: ResourceKey, record: Record) -> None:
        """Run the owning package's key-aware validator, if it declared one."""
        family = self.family_of(record)
        if family.validate is None:
            return
        try:
            family.validate(key, record)
        except ValueError as exc:
            raise RegistryError(f"{key}: {family.name}: {exc}") from exc

    def check_transition(self, key: ResourceKey, current: Record,
                         proposed: Record) -> None:
        """Apply the family's own monotone-transition rule to a write."""
        family = self.family_of(proposed)
        if family.transition is not None:
            family.transition(key, current, proposed)

    def merge_at(self, key: ResourceKey, current: Record,
                 proposed: Record) -> Record:
        """Join a proposal onto the record standing at a key (H4 W2).

        Returns ``proposed`` untouched for a family that declared no
        merge, so the caller has one shape and the compare-and-swap
        default stays the absence of a declaration rather than a branch.
        The family's own exception passes through: the tile map's
        ``CertificateConflict`` is a lawful data event and must reach the
        orchestrator's terminal-fact path, not be re-wrapped here.
        """
        family = self.family_of(proposed)
        if family.merge is None:
            return proposed
        merged = family.merge(key, current, proposed)
        if type(merged) is not type(proposed):
            raise RegistryError(
                f"{key}: {family.name}'s merge returned "
                f"{type(merged).__name__}")
        return merged

    def references_of(self, key: ResourceKey,
                      record: Record) -> tuple[ResourceKey, ...]:
        """The record keys one proposed fact stands on (F-07, relational).

        A declaration, not a lookup: the family reads its own fields and
        names keys. Whether those keys EXIST is the commit wall's
        question, because only the wall holds the decided batch and the
        store at once (see the module docstring).
        """
        family = self.family_of(record)
        if family.references is None:
            return ()
        return family.references(key, record)

    def collections_for(self, key: ResourceKey,
                        record: Record | None) -> tuple[ResourceKey, ...]:
        """The membership resources one durable fact belongs to (M4).

        A key with no record is a member of nothing — the resource table
        computes a JOIN as ``after - before``, so an absent ``before`` is
        what makes the arrival of a key a bump.
        """
        if record is None:
            return ()
        family = self.family_of(record)
        if family.collections is None:
            return ()
        return family.collections(key, record)


def compose(*groups: Sequence[RecordFamily]) -> RecordRegistry:
    """Build one registry from the packages' published family tuples."""
    return RecordRegistry([family for group in groups for family in group])


__all__ = ["RecordFamily", "RecordRegistry", "RegistryError",
           "UnknownRecordError", "compose"]

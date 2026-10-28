"""The transient resource table (DESIGN §5.6): the wake/idle index.

``key -> (value, version, subscribers)``. The table is an accelerator and
carries **no authority** (L13): it is rebuilt in full from the store plus
the sleeping workers' declared read-sets, and any disagreement with the
store is a table bug, never a state fact.

Two entry sources, and both matter:

- every durable record (value, its durable version, its subscribers);
- every key some sleeping worker declared a read on, even if no record
  exists yet — such an entry holds ``value=None`` at ``version=0``
  (``ABSENT_VERSION``), so a key's *arrival* is an ordinary version bump
  and wakes its subscribers like any other change.

Subscriber sets are stored as sorted tuples: DESIGN requires
deterministic iteration order everywhere, and set order is not.

**Collections (M4/OR-7).** A third entry source arrived in R1: a
*collection* key whose version is the number of members it holds. WHICH
collections a fact joins is the owning package's declaration, read through
the record registry (R3) — the table never dispatches on a kind it knows
by name. Collections have no record and are
never written — the table derives them, both incrementally at commit and
in full at ``rebuild``, which is exactly what "the table is an
accelerator with no authority" already promised. They exist because a
subscriber index can only wake on keys a worker already named, and a
worker cannot name an observation piece that does not exist yet; naming
the collection turns an arrival into an ordinary version bump.

Deriving membership and publishing it are two calls, not one
(:meth:`ResourceTable.joined_collections`, :meth:`publish_write`): the
membership callback belongs to the package that owns the family and can
refuse, and the publication-order law (DESIGN §6) puts every fallible
step before the store is durable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .identity import ABSENT_VERSION, ReadSet
from .keys import Record, ResourceKey, WorkId
from .registry import RecordRegistry


@dataclass(frozen=True)
class ResourceEntry:
    """One resource as the scheduler sees it: :meth:`ResourceTable.entry`'s value.

    It used to double as the unit of the table's comparison apparatus
    (``snapshot()``/``__eq__``/``__len__``), which the 2026-08-12 W-B/B3
    ruling deleted as test-facing sugar; what survives is the per-key read
    the ruling kept, so this stays as its declared type.
    """

    version: int
    value: Record | None
    subscribers: tuple[WorkId, ...] = ()


class ResourceTable:
    """Transient index over the durable state. Rebuildable, never authoritative."""

    def __init__(self, registry: RecordRegistry) -> None:
        self._registry = registry
        self._values: dict[ResourceKey, Record | None] = {}
        self._versions: dict[ResourceKey, int] = {}
        self._read_sets: dict[WorkId, ReadSet] = {}
        self._subscribers: dict[ResourceKey, set[WorkId]] = {}

    # -- construction ------------------------------------------------------

    @classmethod
    def rebuild(cls, records: Mapping[ResourceKey, Record],
                versions: Mapping[ResourceKey, int],
                subscriptions: Mapping[WorkId, ReadSet],
                registry: RecordRegistry) -> "ResourceTable":
        """Rebuild the whole table from durable state (§10.1 resume)."""
        table = cls(registry)
        for key in sorted(records):
            record = records[key]
            table.publish_write(key, record, versions[key],
                                table.joined_collections(key, record))
        for worker_id in sorted(subscriptions):
            table.subscribe(worker_id, subscriptions[worker_id])
        return table

    # -- reads -------------------------------------------------------------

    def entry(self, key: ResourceKey) -> ResourceEntry:
        return ResourceEntry(
            version=self._versions.get(key, ABSENT_VERSION),
            value=self._values.get(key),
            subscribers=self.subscribers(key),
        )

    def version(self, key: ResourceKey) -> int:
        return self._versions.get(key, ABSENT_VERSION)

    def value(self, key: ResourceKey) -> Record | None:
        return self._values.get(key)

    def versions(self) -> dict[ResourceKey, int]:
        return dict(self._versions)

    def subscribers(self, key: ResourceKey) -> tuple[WorkId, ...]:
        return tuple(sorted(self._subscribers.get(key, ())))

    def read_set(self, worker_id: WorkId) -> ReadSet:
        return self._read_sets.get(worker_id, ())

    def read_sets(self) -> dict[WorkId, ReadSet]:
        return dict(self._read_sets)

    def keys(self) -> tuple[ResourceKey, ...]:
        """Every key the table holds a version or a subscriber for.

        Includes derived collection keys, which hold a version and no
        value — a comparison that skipped them would call two tables
        equal while their wake behaviour differed.
        """
        return tuple(sorted(set(self._versions) | set(self._subscribers)))

    def wakes_for(self,
                  changed_keys: Iterable[ResourceKey]) -> tuple[WorkId, ...]:
        """Workers subscribed to any changed key, deterministically ordered."""
        woken: set[WorkId] = set()
        for key in changed_keys:
            woken.update(self._subscribers.get(key, ()))
        return tuple(sorted(woken))

    # -- maintenance (driven by the commit layer) -------------------------

    def joined_collections(self, key: ResourceKey,
                           record: Record) -> tuple[ResourceKey, ...]:
        """The collections this write WOULD join — a pure query.

        Membership is the owning package's declaration and its callback
        reads the KEY, so it can refuse. Under the publication-order law
        (DESIGN §6) the whole collection delta is therefore derived here,
        while the batch can still be refused whole; publication itself
        must not be able to fail.
        """
        before = set(self._registry.collections_for(key, self._values.get(key)))
        return tuple(sorted(
            set(self._registry.collections_for(key, record)) - before))

    def publish_write(self, key: ResourceKey, record: Record, version: int,
                      joined: tuple[ResourceKey, ...]) -> None:
        """Publish one committed write from the already-derived delta.

        Infallible by construction: the collections it grows were computed
        by :meth:`joined_collections` before anything moved, and
        membership only ever grows.
        """
        self._values[key] = record
        self._versions[key] = version
        for collection in joined:
            self._versions[collection] = self._versions.get(
                collection, ABSENT_VERSION) + 1

    def subscribe(self, worker_id: WorkId, keys: ReadSet) -> None:
        """Replace a worker's declared read-set (empty = unsubscribe)."""
        for key in self._read_sets.pop(worker_id, ()):
            holders = self._subscribers.get(key)
            if holders is not None:
                holders.discard(worker_id)
                if not holders:
                    del self._subscribers[key]
        if not keys:
            return
        self._read_sets[worker_id] = keys
        for key in keys:
            self._subscribers.setdefault(key, set()).add(worker_id)

    # The table carries no comparison apparatus (W-B/B3, 2026-08-12):
    # ``snapshot()``, ``__eq__`` and ``__len__`` were production-dead sugar
    # for one gate. The property they served — a rebuilt table reproduces a
    # live one — is the explicit triple ``(versions(), read_sets(),
    # subscribers per key)``, asserted in ``tests/core/test_resources.py``,
    # and every term of it is a read this class already publishes.

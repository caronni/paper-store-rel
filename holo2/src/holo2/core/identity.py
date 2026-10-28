"""Read-sets, attempt identity, spend-once, idleness (DESIGN §7).

One mechanism, integer compares only:

- A **read-set** is the exact set of keyed inputs a worker consumes,
  canonically sorted and deduplicated.
- The **attempt identity** IS that read-set paired with the version each
  key had at read time: ``tuple[(key, version), ...]``, sorted by key so
  equality is order-independent. Absent keys read as
  ``ABSENT_VERSION`` (0) — a worker may legally subscribe to a key that
  does not exist yet, and its arrival is a version bump like any other.
- **Spend-once**: a ``(worker_id, route, identity)`` is attempted at most
  once. The ledger is durable in the envelope, so identities survive
  resume and trace replay (§7, user ruling 2026-08-09).
- **Idle** ≡ "current versions equal a spent identity" — no hashing, no
  content compare. A version bump on ANY read key produces a new
  identity, which is unspent, which re-arms the worker.

- **The ledger folds to the latest** (D1, ruled 2026-08-10): one row per
  ``(worker_id, route)`` — newest identity, outcome, attempt count. No
  digests; versions stay the mechanism, and since the hash-free identity
  law retired ``MintRef.attempt_digest`` there is no ``identity_digest``
  either: an attempt is NAMED by the ledger row ``(worker, route)`` its
  values already key, and a digest of that is a name nobody can read
  back. `DESIGN.md` carries the law.
  ``exposures`` is the one MONOTONE counter the fold may never lose:
  attempts that consumed a false-accept budget draw (the worker flags
  them) accumulate even when a later outcome overwrites the row, because
  a budget once drawn is drawn — the 2026-08-11 review proved the
  latest-outcome filter alone silently erased landed CRC exposure.

``SpendRecord`` carries no serialiser of its own: it is a frozen
dataclass of typed fields, so ``core.codec``'s ``encode_dataclass`` /
``decode_dataclass`` ARE its wire form (byte-identical to the pair they
replaced — pinned in ``tests/core/test_identity.py``). The hand-written
pair re-spelled the codec's own key-set and type checks, and the one
substantive invariant — canonical identity, ``0 <= exposures <=
attempts`` — is enforced in :meth:`SpendRecord.__post_init__`, which runs
however the value was built. Validation at the commit wall, not in a
second deserialiser (store-trust doctrine).

Choices where DESIGN is silent (for adjudication):

- Re-recording the identity already held raises ``SpendConflict`` (loud)
  rather than silently folding: a second attempt at a spent identity is
  a scheduling bug, and H1 has no schedule to excuse it.
- ``attempts`` counts attempts on the pair, not distinct identities, and
  nothing in the receiver path reads it.
- ``outcome`` is a free string, as §5.5 wrote it; the commit layer never
  interprets it.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping, TypeAlias

from .keys import AttemptIdentity, ResourceKey, WorkId

ReadSet: TypeAlias = tuple[ResourceKey, ...]

ABSENT_VERSION = 0


class SpendConflict(RuntimeError):
    """A ``(worker_id, route)`` was spent twice at one identity, or backwards."""


def read_set(keys: Iterable[ResourceKey]) -> ReadSet:
    """Canonical read-set: sorted, deduplicated."""
    return tuple(sorted(set(keys)))


def attempt_identity(keys: Iterable[ResourceKey],
                     versions: Mapping[ResourceKey, int]) -> AttemptIdentity:
    """Bind a read-set to the versions it read (§7)."""
    return tuple(
        (key, versions.get(key, ABSENT_VERSION)) for key in read_set(keys)
    )


def drop_kinds(identity: AttemptIdentity,
               kinds: frozenset[str]) -> AttemptIdentity:
    """The identity with whole key KINDS projected out (H4 W2).

    Used by the staleness test alone: a key whose family declared a
    commutative merge is joined at the wall, so its version moving under
    a fire in flight is not staleness — there is nothing for that fire to
    be stale ABOUT. The projection is applied to both sides of one
    comparison and never stored: the durable spend identity keeps every
    key the worker read, which is what keeps "what it read is what it
    spent" true.
    """
    if not kinds:
        return identity
    return tuple((key, version) for key, version in identity
                 if key.kind not in kinds)


def require_canonical_identity(identity: AttemptIdentity) -> None:
    """An identity must be sorted by key and unique, or equality lies."""
    keys = tuple(key for key, _ in identity)
    if any(later <= earlier for earlier, later in zip(keys, keys[1:])):
        raise ValueError(
            "attempt identity must be sorted by key and unique, got "
            f"{[str(key) for key in keys]}")


def fold_refusal(held: AttemptIdentity,
                 proposed: AttemptIdentity) -> str | None:
    """Why ``proposed`` may not replace ``held``, or None if it may.

    Monotone versions are the whole argument for folding, so the fold
    checks them rather than assuming them: every key at or above, at
    least one above, a key named by only one identity reading as
    ``ABSENT_VERSION`` on the other (which is what makes a DROPPED read
    key a regression instead of an invisible one).
    """
    before = dict(held)
    after = dict(proposed)
    advanced = False
    for key in sorted(set(before) | set(after)):
        was = before.get(key, ABSENT_VERSION)
        now = after.get(key, ABSENT_VERSION)
        if now < was:
            return (f"{key} reads v{now} where the spent identity read "
                    f"v{was} (a read-set may not shrink or regress)")
        advanced = advanced or now > was
    return None if advanced else "no read key advanced"


@dataclass(frozen=True)
class SpendRecord:
    """The durable spend held for one ``(worker, route)``: latest, counted.

    ``exposures`` counts the attempts on this row that consumed a
    false-accept budget draw (for payload: ran a decoder, hence one
    CRC-32 comparison landed in state). It accumulates as a monotone
    counter across the fold — the latest outcome may overwrite, the drawn budget
    may not.
    """

    worker_id: WorkId
    route: str
    identity: AttemptIdentity
    outcome: str
    attempts: int = 1
    exposures: int = 0

    def __post_init__(self) -> None:
        require_canonical_identity(self.identity)
        if self.attempts < 1:
            raise ValueError("a spend record counts at least one attempt")
        if not 0 <= self.exposures <= self.attempts:
            raise ValueError(
                "a spend record's exposures count attempts that drew the "
                "budget: 0 <= exposures <= attempts")

    def sort_key(self) -> tuple[WorkId, str]:
        return (self.worker_id, self.route)


class SpendLedger:
    """The durable spend registry: one row per ``(worker, route)``.

    Mutated only by the commit layer, which pre-checks with :meth:`check`
    so a refusal lands before any part of a batch is applied.
    """

    def __init__(self) -> None:
        self._by_route: dict[tuple[WorkId, str], SpendRecord] = {}

    @classmethod
    def restored(cls, records: Iterable[SpendRecord]) -> "SpendLedger":
        """The ledger a cache load hands back: rows TAKEN, never re-folded.

        A durable row is already the fold's result — its identity is the
        latest and its counters accumulated on the way — so replaying it
        through :meth:`record` would fold a row into itself and count its
        attempts twice. The load path takes the rows as they stand; that
        they are lawful is the commit wall's statement, made when they were
        written (F-16 rider r1).
        """
        ledger = cls()
        ledger._by_route = {(row.worker_id, row.route): row for row in records}
        return ledger

    def held(self, worker_id: WorkId, route: str) -> SpendRecord | None:
        """The spend this pair currently stands at, or None."""
        return self._by_route.get((worker_id, route))

    def check(self, spend: SpendRecord) -> None:
        """Refuse a spend the fold may not take; silent if it may."""
        held = self._by_route.get((spend.worker_id, spend.route))
        if held is None:
            return
        if held.identity == spend.identity:
            raise SpendConflict(
                f"{spend.worker_id}/{spend.route}: identity already spent")
        refusal = fold_refusal(held.identity, spend.identity)
        if refusal is not None:
            raise SpendConflict(
                f"{spend.worker_id}/{spend.route}: proposed identity is not "
                f"newer than the spent one — {refusal}")

    def record(self, spend: SpendRecord) -> None:
        """Fold a spend in: latest identity wins, the counters accumulate."""
        self.check(spend)
        held = self._by_route.get((spend.worker_id, spend.route))
        self._by_route[(spend.worker_id, spend.route)] = (
            spend if held is None
            else replace(spend, attempts=held.attempts + 1,
                         exposures=held.exposures + spend.exposures))

    def is_spent(self, worker_id: WorkId, route: str,
                 identity: AttemptIdentity) -> bool:
        held = self._by_route.get((worker_id, route))
        return held is not None and held.identity == identity

    def spends_for(self, worker_id: WorkId,
                   route: str) -> tuple[SpendRecord, ...]:
        """The pair's held spend, as a tuple so callers stay uniform."""
        held = self._by_route.get((worker_id, route))
        return () if held is None else (held,)

    def entries(self) -> tuple[SpendRecord, ...]:
        """All spends in a deterministic order."""
        return tuple(sorted(self._by_route.values(), key=SpendRecord.sort_key))

    def __len__(self) -> int:
        return len(self._by_route)


def is_idle(ledger: SpendLedger, worker_id: WorkId, route: str,
            keys: Iterable[ResourceKey],
            versions: Mapping[ResourceKey, int]) -> bool:
    """§7 idle test: current versions equal an already-spent identity."""
    return ledger.is_spent(worker_id, route, attempt_identity(keys, versions))

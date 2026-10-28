"""The commit layer: the single serial point (DESIGN §10.1, §11.4).

A ``CommitBatch`` is a transactional proposal. Applying it either takes
effect whole or refuses whole — in particular **a spend becomes durable
iff its outcome does**, because both ride the same ``StoreDelta``.

**The publication-order law** (DESIGN §6, user ruling 2026-08-11) is the
shape of ``apply``: the COMPLETE delta — adjudicated writes, the owning
families' key-aware validation, the collection membership those writes
grow, spends, subscriptions, bulk references — is derived and validated
BEFORE anything moves, and then the resource table and the store publish
from that one delta. Nothing fallible runs after durable apply, so a
refused batch leaves nothing durable and nothing in memory.

Rules, in the order the layer enforces them:

1. A terminal ``CloseRecord`` freezes the session: every later batch
   refuses (``TerminalSessionError``), spends and subscriptions included.
   The wall reads the LIVE table, so the close this rule speaks of is
   whichever one ``store._fold_close`` ADMITTED into it (OR-13,
   2026-08-22): a SKIPPED close (`--no-close`) and a SUPERSEDED one
   (commits recorded after it) are not admitted. The rule therefore
   stays true as written rather than merely mostly-true — nothing ever
   committed after a close that was still the last word.
2. A batch may write a key at most once (``DuplicateWrite``); a record
   must match its key's kind, and the family's own validator sees the KEY
   (a record whose identity disagrees with the key it is stored under is
   an illegal durable state, refused here and at load).
3. **A merge-declaring family is JOINED, not compare-and-swapped** (H4
   W2's first concurrency ruling). Before anything is identified, every
   write whose family declared a ``merge`` hook is re-applied against the
   record the store CURRENTLY holds — an atomic fetch-and-union inside
   this serial section, microseconds of set work, no lock anywhere near a
   worker. The batch that is then adjudicated, identified and journaled
   carries the POST-MERGE record, which is what makes the fold a
   state transfer: replay re-applies the recorded result verbatim and
   never has to re-derive a join from a snapshot it no longer holds.
   Nothing changes for any other family, and nothing changes for a serial
   run of a merging one: there the store still holds the snapshot the
   fire read, so ``current ⊔ proposal`` IS the proposal and the batch id
   is the one the fire computed.
4. **Version bumps iff content changed.** Equality compare for records
   (blob refs are content addresses, so equality is content equality even
   for bulk values — which makes equality DECISIVE for every family, so
   the force-a-bump escape ``content_changed=True`` was deleted in the
   H3.5 sweep: no production writer ever passed it, and F-26 named it as
   a test-only wart on the one law that keeps wakes honest).
5. **A record's named records EXIST** (F-07's relational half). A family
   declares the keys its record stands on (``RecordFamily.references``)
   and the wall resolves them against the DECIDED BATCH plus the store,
   so a certificate's pose, a piece's calibration or a window's region is
   a fact by the time the write naming it lands. It is the sibling of
   rule 9's bulk check — a dangling reference is a wrong writer either
   way — and it lives here rather than in a validator because a validator
   may not read other records (``registry``, the ``validate`` contract).
6. Monotone facts stay monotone, and structural validators hold. Both are
   the **record registry's** (R3): a family declares its own transition
   rule and its own structural validator, and this layer applies whichever
   the owning package registered. The tile map's "state may not regress,
   certified content may not change" (``CertificateConflict``, L5/§11.3)
   is unchanged — it just lives in ``solve.records`` now, where a
   certificate is something the code is allowed to know about. On a
   family that ALSO declared a merge the two compose in one direction
   only: the transition runs on the MERGED record, so it audits the join
   rather than the proposal (rule 3, and ``registry``'s own statement).
7. Spends are pre-checked against the durable ledger and against the
   batch itself, so a ``SpendConflict`` refuses before anything is
   applied. The ledger folds to one row per ``(worker, route)`` (D1), so
   the batch-level check is on that PAIR: two identities for one pair in
   one batch is an ordering the durable state cannot express.
8. Subscriptions are applied **before** wakes are computed, so a worker
   that goes to sleep in the same commit that changes one of its read
   keys is woken rather than lost. Over-waking is waste; the idle test
   costs integer compares and refuses to re-run anything.
9. **Staged bulk values are materialised here** (R1/M6), after the delta
   is validated and before it is published — the store's durability
   contract already required blobs to be appended strictly before the
   commit that references them, and a failure there leaves inert orphan
   bytes rather than a durable fact. A proposal the orchestrator discards
   is never materialised at all, and a batch naming bulk nobody carried
   refuses without touching the sidecar (references resolve against
   staged + stored).
10. **Collections grow with their members** (R1/M4). A write that makes
   its key JOIN a collection bumps that collection's derived version and
   the collection key joins ``changed_keys``, so a worker subscribed to
   "the evidence on this tile" or "the certified frontier" wakes on an
   arrival it could not have named. Collections carry no record and no
   authority; the resource table derives them (``resources.py``) — and
   derives them UP FRONT, because that derivation runs the owning
   package's callback and can refuse.

DESIGN §10.1 names the batch ``{writes, spends, wakes}``. Wakes are
*derived* — they are the changed-key set joined against the subscriber
index — so they are returned in ``CommitResult``, and the third proposal
member is the durable ``subscriptions`` declaration wakes are computed
from. (Choice, for adjudication.)

H1 is single-threaded and deterministic: no locks, no clocks, no RNG.
Concurrency arrives in H3 and lands *outside* this layer — the serial
commit point is the design.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Sequence

from .blobs import StagedBlob
from .codec import digest_json, encode_dataclass, encode_typed_record
from .identity import (ReadSet, SpendConflict, SpendRecord, attempt_identity,
                       drop_kinds, read_set)
from .keys import AttemptIdentity, Record, ResourceKey, WorkId
from .records import blob_refs
from .registry import RegistryError
from .resources import ResourceTable
from .store import Store, StoreDelta
from .trace import TraceEvent, TraceWriter


class CommitRefusal(RuntimeError):
    """A batch was refused whole; no part of it took effect.

    FATAL, and deliberately so (the F-08 review dialogue): a refusal here
    says a writer proposed a state the wall's laws forbid, which is a
    DEFECT in that writer — the crash is the feature, and a caught-and-
    continued refusal would leave a run silently doing less than it
    reports. Exactly ONE subclass is a lawful data event rather than a
    bug, and it is the only one anything in this tree catches:
    :class:`CertificateConflict`.
    """


class TerminalSessionError(CommitRefusal):
    """The session's CloseRecord is terminal; nothing may be written."""


class CertificateConflict(CommitRefusal):
    """Certified content changed — a DATA integrity event (L5, F-11).

    NOT a code bug, which is what separates it from every other
    :class:`CommitRefusal`: lawful code produces this the day two
    independent decodes of one work key disagree — a ~2^-32 CRC false
    accept, or a scissors session whose captures came off different
    physical sheets. Nothing about the writer is wrong; the DATA
    contradicts itself, and a certificate is never voted on (L5).

    So this refusal alone is caught — by the orchestrator's serial commit
    path, which turns it into the one lawful terminal write
    (``CloseRecord(integrity_failure)`` carrying this exception's own
    message, which names the key and what differed) and ends the run.
    The lineage is frozen from that commit on; adding captures and
    rerunning cannot revise it.
    """


class StateRegression(CommitRefusal):
    """A monotone fact moved backwards — a writer defect, and fatal."""


class DuplicateWrite(CommitRefusal):
    """One batch wrote the same key twice."""


@dataclass(frozen=True)
class Write:
    """A proposed record at a key, with the optional producer change flag."""

    key: ResourceKey
    record: Record

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key.to_json(),
            **encode_typed_record(self.record),
        }


#: A route spent by a worker under one attempt identity (§7). Proposing a
#: spend and holding one are the same fact — the proposal carried no field
#: the durable record lacks, and re-validating the identity on the way
#: across cost one canonicality check per spend.
SpendProposal = SpendRecord


@dataclass(frozen=True)
class Subscription:
    """A sleeping worker's declared read-set (empty = unsubscribe)."""

    worker_id: WorkId
    read_set: ReadSet = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id.to_json(),
            "read_set": [key.to_json() for key in self.read_set],
        }


@dataclass(frozen=True)
class CommitBatch:
    """One transaction. Canonicalized before it is identified or applied."""

    writes: tuple[Write, ...] = ()
    spends: tuple[SpendProposal, ...] = ()
    subscriptions: tuple[Subscription, ...] = ()
    blobs: tuple[StagedBlob, ...] = ()

    def canonical(self) -> "CommitBatch":
        """Sorted deterministically; ordering within a batch is not meaning."""
        return CommitBatch(
            writes=tuple(sorted(self.writes, key=lambda w: w.key)),
            # Sorted by VALUES — worker id, route, then the identity
            # itself, which is a tuple of (key, version) and orders like
            # one. The digest this tiebreak used to take was the last
            # hash in the tree that named something other than content.
            spends=tuple(sorted(
                self.spends,
                key=lambda s: (s.worker_id, s.route, s.identity))),
            subscriptions=tuple(sorted(
                self.subscriptions, key=lambda s: s.worker_id)),
            blobs=tuple(sorted(
                {blob.ref.sha256: blob for blob in self.blobs}.values(),
                key=lambda blob: blob.ref.sha256)),
        )

    def to_json(self) -> dict[str, Any]:
        """This batch as it stands — canonicalize first if the id is wanted."""
        return {
            "writes": [write.to_json() for write in self.writes],
            "spends": [encode_dataclass(spend) for spend in self.spends],
            "subscriptions": [sub.to_json() for sub in self.subscriptions],
            # Content addresses only: the payloads are already identified
            # by them, and a batch that stages bytes nothing references is
            # still a different batch from one that does not.
            "blobs": [blob.ref.sha256 for blob in self.blobs],
        }


def batch_id(batch: CommitBatch) -> str:
    """Content-derived batch name (§10.2); the journal's ordering token."""
    return digest_json(batch.canonical().to_json())


@dataclass(frozen=True)
class CommitResult:
    """What a commit did: the changed-key set and the wakes it implies."""

    commit_seq: int
    batch_id: str
    changed_keys: tuple[ResourceKey, ...] = ()
    wakes: tuple[WorkId, ...] = ()


class CommitEngine:
    """Applies batches serially against one store and its resource table."""

    def __init__(self, store: Store, *, table: ResourceTable | None = None,
                 trace: TraceWriter | None = None) -> None:
        self._store = store
        self._registry = store.registry
        self._table = table if table is not None else ResourceTable.rebuild(
            store.records(), store.versions(), store.subscriptions(),
            store.registry)
        self._trace = trace

    @property
    def store(self) -> Store:
        return self._store

    @property
    def table(self) -> ResourceTable:
        return self._table

    # -- worker-side helpers ----------------------------------------------

    def attempt_identity(self, keys: Sequence[ResourceKey]) -> AttemptIdentity:
        """Bind a read-set to the versions the table currently holds (§7)."""
        return attempt_identity(keys, self._table.versions())

    def is_current(self, keys: Sequence[ResourceKey],
                   identity: AttemptIdentity) -> bool:
        """Is a proposal's identity the one it would take NOW (§7)?

        The staleness test the scheduler admits on, and the other half of
        the merge ruling: a key whose family declared a ``merge`` is
        projected OUT of both sides, because the wall JOINS that key at
        commit time and a join has no stale input. Guarding a commutative
        record with compare-and-swap manufactures a conflict that does not
        semantically exist — the proposal would be discarded, its gains
        thrown away, and the same fire re-run to re-derive them.

        Everything else keeps compare-and-swap exactly as it was, and the
        SPEND identity is untouched: what a worker read is still what it
        spent, so a later gain on a joined key still re-arms it. Only the
        admit-or-discard decision moves.
        """
        return drop_kinds(self.attempt_identity(keys),
                          self._registry.merge_kinds()) == drop_kinds(
                              identity, self._registry.merge_kinds())

    def is_idle(self, worker_id: WorkId, route: str,
                keys: Sequence[ResourceKey]) -> bool:
        """§7 idle test: is this worker's current identity already spent?"""
        return self._store.ledger.is_spent(
            worker_id, route, self.attempt_identity(keys))

    def settled_id(self, batch: CommitBatch) -> str:
        """The id this batch WOULD take if it were applied right now.

        Pure: it settles the merges against the store and digests, and
        touches nothing. Replay needs it because the recorded id is the
        POST-MERGE one (rule 3) while a re-run fire proposes the same
        PRE-merge batch it proposed before — the two agree exactly when
        no race intervened, which is exactly when they may not be
        compared naively. Matching held proposals to a recorded commit is
        the one caller.
        """
        return digest_json(self._settle_merges(batch.canonical()).to_json())

    # -- the serial point --------------------------------------------------

    def apply(self, batch: CommitBatch) -> CommitResult:
        """Apply one transactional batch; return the changed-key set.

        The publication-order law: derive and validate the COMPLETE delta
        — merge-declaring writes JOINED onto what stands (rule 3), the
        rest adjudicated against their families' key-aware validators
        and transition rules, the collection membership those writes grow,
        spends pre-checked against the ledger, subscriptions canonical,
        bulk references resolved against staged + stored — and only then
        publish it. Two consequences the tests pin: a refused batch leaves
        nothing durable AND nothing moved in memory, and the store's one
        remaining failure (the snapshot, which is durability, not
        semantics) cannot leave the table disagreeing with it, because
        both halves publish from the same delta and the table goes first.
        """
        if self._store.is_terminal():
            raise TerminalSessionError(
                "session is terminal; its CloseRecord is immutable (§5.5)")
        canonical = self._settle_merges(batch.canonical())
        identifier = digest_json(canonical.to_json())     # already canonical
        writes = self._adjudicate_writes(canonical.writes)
        self._require_references(writes)
        joined = {key: self._table.joined_collections(key, record)
                  for key, record, _version in writes}
        spends = self._adjudicate_spends(canonical.spends)
        subscriptions = tuple(
            (sub.worker_id, read_set(sub.read_set))
            for sub in canonical.subscriptions)
        self._require_bulk_present(writes, canonical.blobs)

        # The delta is complete and validated. Materialising staged bulk is
        # the last step that can fail, and it is deliberately outside the
        # publication below: a failure there leaves inert orphan bytes the
        # sidecar dedups on the re-arm, never a durable fact.
        for blob in canonical.blobs:
            self._store.put_staged(blob)          # strictly before the commit

        # -- publication: one delta, both receivers, nothing fallible ------
        for worker_id, keys in subscriptions:
            self._table.subscribe(worker_id, keys)
        for key, record, version in writes:
            self._table.publish_write(key, record, version, joined[key])
        self._store.apply_committed(
            StoreDelta(writes=writes, spends=spends,
                       subscriptions=subscriptions), identifier)

        collections = sorted({collection for group in joined.values()
                              for collection in group})
        changed_keys = tuple(key for key, _, _ in writes) + tuple(collections)
        wakes = self._table.wakes_for(changed_keys)
        result = CommitResult(
            commit_seq=self._store.commit_seq,
            batch_id=identifier,
            changed_keys=changed_keys,
            wakes=wakes,
        )
        self._record_trace(result, writes)
        return result

    # -- internals ---------------------------------------------------------

    def _settle_merges(self, canonical: CommitBatch) -> CommitBatch:
        """Join every merge-declaring write onto the record standing NOW.

        The first thing the serial section does, and the reason the whole
        ruling costs no lock: the fire ran snapshot-based and lock-free,
        and what crosses the wall is its OPERATION — for a join
        semilattice, the proposal itself. Re-applying it here against
        ``current`` is an atomic fetch-and-union of a few sorted tuples.

        The batch this returns is what everything downstream sees: the
        adjudicator, the identifier, the journal, the cache. That is the
        state-transfer half of the ruling — a replay re-applies the
        RESULT and never re-derives a join against a store it has moved
        past.

        Substitution only, never refusal: a write whose record type,
        kind or key disagrees is left exactly as proposed, so the ordinary
        adjudication below raises the ordinary refusal with the message it
        already has. The one exception that DOES leave here is the
        family's own — a join that cannot join (``CertificateConflict``).

        Canonicality survives: only records change, never the key order a
        sort by key already fixed.
        """
        if not self._registry.merge_kinds():
            return canonical
        settled: list[Write] = []
        changed = False
        for write in canonical.writes:
            merged = self._merged(write)
            changed = changed or merged is not write.record
            settled.append(write if merged is write.record
                           else Write(write.key, merged))
        if not changed:
            return canonical
        return replace(canonical, writes=tuple(settled))

    def _merged(self, write: Write) -> Record:
        """One write's post-merge record — or its own, when nothing joins."""
        key = write.key
        if key.kind not in self._registry.merge_kinds():
            return write.record
        current = self._store.get(key)
        if current is None or type(current) is not type(write.record):
            return write.record       # nothing to join, or a refusal below
        try:
            # The proposal is a record in its own right and is validated as
            # one BEFORE it is used as an operand: a join may normalise a
            # malformed input into a lawful output, and a wrong writer must
            # not be laundered by the merge it feeds.
            self._registry.validate(key, write.record)
        except RegistryError as exc:
            raise CommitRefusal(str(exc)) from exc
        try:
            return self._registry.merge_at(key, current, write.record)
        except RegistryError as exc:
            raise CommitRefusal(str(exc)) from exc

    def _adjudicate_writes(self, writes: Sequence[Write],
                           ) -> tuple[tuple[ResourceKey, Record, int], ...]:
        decided: list[tuple[ResourceKey, Record, int]] = []
        seen: set[ResourceKey] = set()
        for write in writes:
            key = write.key
            if key in seen:
                raise DuplicateWrite(f"{key}: written twice in one batch")
            seen.add(key)
            try:
                kind = self._registry.kind_of(write.record)
                self._registry.validate(key, write.record)
            except RegistryError as exc:
                raise CommitRefusal(str(exc)) from exc
            if key.kind != kind:
                raise CommitRefusal(
                    f"{key}: {type(write.record).__name__} may not be stored "
                    f"under kind {key.kind!r}")
            current = self._store.get(key)
            if current is not None:
                _require_same_type(key, current, write.record)
                self._registry.check_transition(key, current, write.record)
                if current == write.record:
                    continue                      # no change ⇒ no bump, no wake
            decided.append((key, write.record, self._store.version(key) + 1))
        return tuple(decided)

    def _adjudicate_spends(self, spends: Sequence[SpendRecord],
                           ) -> tuple[SpendRecord, ...]:
        """Pre-check every spend, so the ledger's own fold cannot refuse.

        The batch marker is the ``(worker, route)`` PAIR, not the triple:
        the ledger holds one row per pair, so two identities for one pair
        in one batch is an ordering the durable state cannot express.
        """
        records: list[SpendRecord] = []
        seen: set[tuple[WorkId, str]] = set()
        for spend in spends:
            marker = (spend.worker_id, spend.route)
            if marker in seen:
                raise SpendConflict(
                    f"{spend.worker_id}/{spend.route}: identity spent twice "
                    "in one batch")
            seen.add(marker)
            self._store.ledger.check(spend)
            records.append(spend)
        return tuple(records)

    def _require_references(self,
                            writes: Sequence[tuple[ResourceKey, Record, int]],
                            ) -> None:
        """A record may not name a record nobody committed (F-07).

        The relational half of the domain the wall claims to protect: the
        cheap half proved a record IS what its key says, this proves what
        it STANDS ON is there. Resolved against the DECIDED BATCH plus the
        store, so a producer that mints a pose and the evidence citing it
        in one transaction is lawful — which is exactly the shape every
        real writer already has — while one that cites a pose it forgot to
        write refuses, naming both keys.

        A miss is a WRONG WRITER, so it is an ordinary ``CommitRefusal``
        (fatal) and never a :class:`CertificateConflict`: nothing about
        the data contradicts itself, and the terminal-fact path is for
        contradictions only.

        Once is enough, forever: facts are immutable and are never
        deleted, so a reference that resolves here cannot dangle later.
        The cost is O(references) dict lookups per write on the serial
        path — the sibling of the bulk check right below.
        """
        decided = {key for key, _record, _version in writes}
        for key, record, _version in writes:
            for reference in self._registry.references_of(key, record):
                if reference in decided or self._store.get(reference) is not None:
                    continue
                raise CommitRefusal(
                    f"{key}: {type(record).__name__} names {reference}, "
                    "which no committed record stands at (neither this "
                    "batch nor the store holds it)")

    def _require_bulk_present(self, writes: Sequence[tuple[ResourceKey, Record, int]],
                              staged: Sequence[StagedBlob]) -> None:
        """A record may not reference bulk the store does not hold (M6).

        Staging made the failure mode possible: a producer can compute a
        content address and forget to carry the bytes. Left unchecked that
        commits a dangling reference and fails much later, on a read, in a
        different worker. Checked here it refuses the batch that did it.

        Resolved against the batch's STAGED addresses plus what the
        sidecar already holds, so the check is part of deriving the delta
        and a batch that names bulk nobody carried refuses without
        appending a byte.
        """
        carried = {blob.ref.sha256 for blob in staged}
        dangling = sorted(
            ref.sha256 for _key, record, _version in writes
            for ref in blob_refs(record)
            if ref.sha256 not in carried
            and not self._store.blobs.contains(ref.sha256))
        if dangling:
            raise CommitRefusal(
                f"{len(dangling)} record reference(s) name bulk values that "
                f"were neither staged nor already stored, first {dangling[0]}")

    def _record_trace(self, result: CommitResult,
                      writes: Sequence[tuple[ResourceKey, Record, int]]) -> None:
        """Digest a SAMPLED commit. Observer I/O failure is swallowed (L12).

        The ordering is the journal's now (F-16), so an unsampled commit
        writes nothing here — the trace costs a modulo test per commit and
        a file only when an operator asked for the canary.
        """
        if self._trace is None or not self._trace.should_sample(
                result.commit_seq):
            return
        try:
            self._trace.append(TraceEvent(
                seq=result.commit_seq,
                batch_id=result.batch_id,
                input_sha256=result.batch_id,
                # The type tag rides the entry (``encode_typed_record``):
                # the fields alone let two different record types at one
                # key with equal field values digest the same, which is a
                # blind spot in the very canary this digest IS.
                output_sha256=digest_json([
                    [key.to_json(), version, encode_typed_record(record)]
                    for key, record, version in writes]),
            ))
        except OSError:
            pass          # the trace is disposable; the commit already stands


def _require_same_type(key: ResourceKey, current: Record, proposed: Record) -> None:
    if type(current) is not type(proposed):
        raise CommitRefusal(
            f"{key}: holds {type(current).__name__}, proposed "
            f"{type(proposed).__name__}")

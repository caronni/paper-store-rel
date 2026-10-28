"""The durable session store: one session = one state directory (§5.6).

Directory layout::

    <state_dir>/journal      the fold's starting point + one batch id per commit
    <state_dir>/cache        append-only delta frames — DISPOSABLE (§cache)
    <state_dir>/blobs.bin    append-only content-addressed blob sidecar
    <state_dir>/trace.jsonl  optional sampled digests (observer-side; §10.3)
    <state_dir>/lock         the single-writer claim: pid of the one live
                             owner (F-19). Taken exclusively at create/open,
                             released at close; a lock whose pid is dead is
                             a crash's residue and is taken over silently
                             (the journal tail re-earn IS the recovery).
                             Two LIVE processes on one state dir would
                             interleave journal appends and sidecar frames
                             into garbage no reader could detect until far
                             too late — refused at the door instead.

**Journal-authoritative persistence** (F-16, ruled 2026-08-12). `state =
fold(inputs, code, ordering)`: nothing in a state directory is
authoritative, because the tree's own laws — per-item determinism, L12's
no-clocks, seeded draws, value-bound policy, batch-id-verified replay —
already pay for re-deriving it. So the durable record is the JOURNAL (the
starting point and the commit ordering, fsynced at every commit) and the
state itself is a MEMO: the cache, appended one delta frame per cadence,
never rewritten, and thrown away rather than repaired.

Durability contract:

- The journal is appended and fsynced AT the commit. A crash therefore
  loses at most the commit that was mid-write, and its work re-arms.
- A cache frame is appended every ``snapshot_every`` commits
  (``DEFAULT_SNAPSHOT_EVERY`` = 512, the OR-6 cadence ruling) and at
  :meth:`close`, so a clean exit leaves the memo complete. A crash leaves
  the journal ahead of the cache, and the tail is RE-EARNED by replay —
  crash recovery and the ``--replay`` audit are one code path
  (``engine.orchestrator``), which is F-24's tie between replay and
  durable state.
- Blobs are appended **before** the commit that references them. A crash
  in between leaves an inert orphan blob (§blobs) the re-armed work
  dedups onto.

**What the fold admits of a CLOSE** (the `--no-close` rulings,
2026-08-22; :meth:`Store._fold_close`). The journal is never rewritten
and a close record is never deleted — both rules below decide what the
LIVE TABLE takes from the memo, and the frames keep saying what they
always said:

- *A close is terminal only while it is the last word* (the lead's rule).
  A ``CLOSE_KEY`` write with COMMITS RECORDED AFTER IT is a SUPERSEDED
  close: the fold drops it under every policy, the session is OPEN, and
  the next closing run recomputes the close from the certificates it
  holds and appends a new ``CloseRecord``. That is what keeps the commit
  wall's first rule (a terminal close is immutable) true as written —
  nothing was ever written after a close that was still terminal.
- *Skipping* is the read-time half of `--no-close` (the user's ruling):
  opened with ``skip_close=True``, the fold takes no ``CLOSE_KEY`` record
  at all, so the store is not terminal and the wall admits commits. The
  old close stays in the frames and in the journal; nothing is rewritten,
  and a later ordinary open reads it again (superseded, if this run
  committed anything).
- An ``integrity_failure`` close is neither skipped nor superseded. It is
  the only durable trace of a refused conflicting write (F-11) rather
  than a derivation from the certificate set, so ``skip_close`` REFUSES
  it by name instead of dropping it.

``open`` is a GATE, not an audit (F-16 rider r1): the journal's starting
point must be this build's (schema version, record-family manifest,
session type) and the lineage must be the one the run declares
(``expect_session``, by value); the cache must memoise that same starting
point and may not claim more commits than the journal recorded. Past that
the memo is TRUSTED — there is no per-record re-validation, because a
disposable cache has exactly two honest states, trusted or re-folded, and
checking one's own store against oneself is not a third. Lawfulness is
the commit wall's, and faithfulness is replay's.

**Schema identity (R3).** The store is generic over a
``core.registry.RecordRegistry``: it knows how to hold facts, never what
a fact is. The starting point therefore carries the registry's manifest —
every registered family's name and version — and a state whose manifest
differs from the running build's is refused at open, naming the families
that moved. ``SCHEMA_VERSION`` above it versions the state directory's
own structure; the manifest versions the records inside it.

The store carries no policy and runs no algorithms; the commit layer is
the only writer (H1 is single-threaded — concurrency arrives in H3).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .blobs import BlobSidecar, StagedBlob
from .cache import (CACHE_NAME, CacheError, CachedState, CacheReader,
                    CacheWriter, Interner, spend_read_sets)
from .codec import (CodecError, canonical_json_bytes, decode_dataclass,
                    encode_dataclass, encode_typed_record)
from .identity import ReadSet, SpendLedger, SpendRecord
from .journal import (JOURNAL_MAGIC, JOURNAL_NAME, Journal, JournalError,
                      commit_count, position_after_commits, read_journal,
                      read_starting_point, start_marker)
from .keys import Record, ResourceKey, WorkId
from .records import (BlobRef, CLOSE_KEY, CloseRecord, CloseStatus, blob_refs)
from .registry import RecordRegistry

#: The STATE DIRECTORY's structural version. R3 bumped it to 2 (the
#: manifest and the session type tag joined the header); the D1 fold
#: bumped it to 3; the hash-free identity law bumped it to 4 (durable ids
#: ARE their defining values); F-16 bumps it to 6 — the whole layout
#: moved, from one rewritten ``state.json`` envelope to a journal beside a
#: delta-frame cache. **H4 W2 bumps it to 7**: the journal records
#: DISPATCHES as well as commits (``journal.start_marker``), so a
#: pre-marker journal speaks a different ordering vocabulary — and a
#: pre-marker POOLED one cannot be replayed exactly at all, which is the
#: reason markers exist, so reading it under this build would be claiming
#: a guarantee the file cannot support. Pre-freeze rule: an older state
#: refuses loudly and is never migrated.
SCHEMA_VERSION = 7

#: Commits between cache frames when nobody says otherwise — the OR-6
#: policy value, RULED 512 on 2026-08-12 (W-B/B11). ONE name, relayed by
#: the session and the CLI rather than respelled, so the ruling reaches
#: every caller: core cannot import the composition root, so the
#: operator-facing default is defined at the mechanism and read outwards.
#:
#: 512 is ≈ one frame a minute at the measured real-sheet commit rate
#: (~10/s) and is clock-free (L12 forbids a schedule the wall clock
#: drives). It costs no decode result: M-3.4 measured all seven cadences
#: to identical certificates, payload and counters. Under
#: journal-authoritative persistence it is a cache-freshness knob and not
#: a durability trade — a crash re-earns at most one cadence window.
DEFAULT_SNAPSHOT_EVERY = 512

BLOBS_NAME = "blobs.bin"
TRACE_NAME = "trace.jsonl"

#: The pre-F-16 layout. Named ONLY so a state directory written by an
#: older build refuses with the reason instead of "no journal" (freshness
#: doctrine: the old format is not read, and never quietly).
LEGACY_ENVELOPE_NAME = "state.json"

_STARTING_POINT_FIELDS = frozenset(
    {"magic", "schema_version", "families", "session_type", "session"})


class StoreError(RuntimeError):
    """Refusal at the store's trust boundary (§11.4)."""


@dataclass(frozen=True)
class _Entry:
    """One durable row: the record AND the version it stands at.

    They are one fact, so they live in one table. Held as two dicts they
    were a keyset invariant nothing enforced — every write set both, every
    read that needed a version looked the same key up twice — and "the
    version of a record that is not there" was representable.
    """

    record: Record
    version: int


@dataclass(frozen=True)
class StoreDelta:
    """An already-adjudicated set of durable changes (built by ``commit``)."""

    writes: tuple[tuple[ResourceKey, Record, int], ...] = ()
    spends: tuple[SpendRecord, ...] = ()
    subscriptions: tuple[tuple[WorkId, ReadSet], ...] = ()


LOCK_NAME = "lock"


def _acquire_lock(state_dir: Path) -> None:
    """The single-writer claim (F-19): one live pid owns a state dir.

    O_EXCL is the whole mechanism. A lock naming a LIVE pid refuses at
    the door — two writers would interleave journal appends and sidecar
    frames into garbage detectable only much later. A lock naming a DEAD
    pid is a crash's residue: taken over silently, because the journal
    tail re-earn is already the designed recovery for everything else a
    crash leaves behind.
    """
    path = state_dir / LOCK_NAME
    while True:
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                holder = int(path.read_text().strip() or "0")
            except (OSError, ValueError):
                holder = 0
            if holder > 0 and _pid_alive(holder):
                raise StoreError(
                    f"{state_dir}: state directory is owned by live "
                    f"process {holder} (F-19: one writer). Wait for it, "
                    "or remove the lock file if you are certain it is "
                    "not a holo2 run.") from None
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            continue
        with os.fdopen(handle, "w") as lock:
            lock.write(str(os.getpid()))
        return


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _release_lock(state_dir: Path) -> None:
    try:
        (state_dir / LOCK_NAME).unlink()
    except FileNotFoundError:
        pass


class Store:
    """One session's durable state, over one registered record vocabulary."""

    def __init__(self, state_dir: Path, session: Record,
                 sidecar: BlobSidecar, registry: RecordRegistry, *,
                 journal: Journal, cache: CacheWriter,
                 snapshot_every: int = DEFAULT_SNAPSHOT_EVERY,
                 fsync: bool = True) -> None:
        if type(session) is not registry.session_type:
            raise StoreError(
                f"{type(session).__name__} is not this build's session "
                f"identity ({registry.session_type.__name__})")
        self._dir = state_dir
        self._session = session
        self._registry = registry
        self._sidecar = sidecar
        self._journal = journal
        self._cache = cache
        self._snapshot_every = max(1, snapshot_every)
        self._fsync = fsync
        self._entries: dict[ResourceKey, _Entry] = {}
        self._ledger = SpendLedger()
        self._subscriptions: dict[WorkId, ReadSet] = {}
        self._commit_seq = 0
        #: Where the next JOURNAL ENTRY goes. Commits and dispatches share
        #: one numbering — a marker's position IS the snapshot prefix the
        #: fire it names read — so this is not ``_commit_seq`` and has not
        #: been since H4 W2.
        self._journal_pos = 0
        # What the next cache frame owes: the keys whose row moved and the
        # ledger rows that moved, since the last frame. A delta encoding
        # needs exactly this and nothing else.
        self._dirty: dict[ResourceKey, None] = {}   # ORDERED: see _frame
        self._dirty_spends: set[tuple[WorkId, str]] = set()
        self._dirty_subs: set[WorkId] = set()
        self._uncached = 0
        #: Dispatches recorded but not yet settled. A cache frame is a
        #: RESUME POINT, and a resume point has to be a clean cut through
        #: the dispatches — see :meth:`_frame`.
        self._outstanding = 0
        #: The close the fold declined to admit — :attr:`unadmitted_close`.
        #: A CREATED state has no memo to fold, so it never has one.
        self._unadmitted_close: CloseRecord | None = None

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def create(cls, state_dir: Path, session: Record,
               registry: RecordRegistry, *,
               snapshot_every: int = DEFAULT_SNAPSHOT_EVERY,
               fsync: bool = True) -> "Store":
        """Create a fresh state directory (refuses to overwrite one)."""
        state_dir.mkdir(parents=True, exist_ok=True)
        _refuse_legacy(state_dir)
        _acquire_lock(state_dir)
        # Same discipline ``open`` uses: EVERY failure past the acquire must
        # release the lock (the journal-exists arm used to be the only one
        # that did, so any later failure — a bad header, a disk error in
        # Journal/CacheWriter/BlobSidecar creation, a session-identity
        # mismatch surfacing in the constructor — left the lock behind).
        # ``close()`` owns the release on the success path, same as always.
        try:
            if (state_dir / JOURNAL_NAME).exists():
                raise StoreError(
                    f"{state_dir} already holds a session journal")
            header = starting_point(session, registry)
            journal = Journal.create(state_dir / JOURNAL_NAME, header,
                                     fsync=fsync)
            cache = CacheWriter.create(state_dir / CACHE_NAME, header,
                                       fsync=fsync)
            if fsync:
                _fsync_dir(state_dir)
            sidecar = BlobSidecar.open(state_dir / BLOBS_NAME, fsync=fsync)
            return cls(state_dir, session, sidecar, registry, journal=journal,
                       cache=cache, snapshot_every=snapshot_every,
                       fsync=fsync)
        except BaseException:
            _release_lock(state_dir)
            raise

    @classmethod
    def peek_identity(cls, state_dir: Path,
                      registry: RecordRegistry) -> Record:
        """What this state was STARTED as — read first, own nothing (C5).

        RULINGS G6 (2026-08-22): an operator resuming a session may not
        have to re-type the identity the state holds, and until now
        nothing could tell them what it is — it was reachable only from
        INSIDE :meth:`open`, which needs one to open at all. The
        composition root asks this first and composes from the answer.

        Journal line 1 only, no lock, no cache, no fold, no handle left
        open (``journal.read_starting_point`` argues why that is safe).
        The GATE is :meth:`open`'s own, not a laxer one — magic, schema
        version, family manifest, session type — because a state this
        build cannot open is one whose identity it must not act on
        either. The memo and the ordering are NOT checked: :meth:`open`
        stays the authority on whether the state is any good.
        """
        try:
            header = read_starting_point(state_dir / JOURNAL_NAME)
        except JournalError as exc:
            raise StoreError(str(exc)) from exc
        return _require_starting_point(header, state_dir, registry)

    @classmethod
    def open(cls, state_dir: Path, registry: RecordRegistry, *,
             snapshot_every: int = DEFAULT_SNAPSHOT_EVERY, fsync: bool = True,
             expect_session: Record | None = None,
             skip_close: bool = False) -> "Store":
        """Open an existing state directory: gate the journal, trust the memo.

        ``skip_close`` is the MECHANISM half of the engine's `--no-close`
        policy (2026-08-22): the fold takes no close record, so this
        store is not terminal. Core carries no policy — it carries what
        the fold admits, and the module docstring states the rules.
        """
        _refuse_legacy(state_dir)
        _acquire_lock(state_dir)
        # A refused open is not a claim: EVERY failure past the acquire
        # must release, or the lock names this live pid and a retry in the
        # same process misreports a schema refusal as a second writer. Any
        # journal/sidecar/cache handle already opened on the SAME failure
        # path must close too — a refusal past ``_open_cache`` used to
        # release only the lock and leak all three open fds behind it.
        journal: Journal | None = None
        sidecar: BlobSidecar | None = None
        cache: CacheWriter | None = None
        try:
            try:
                header, ordering = read_journal(state_dir / JOURNAL_NAME)
            except JournalError as exc:
                raise StoreError(str(exc)) from exc
            session = _require_starting_point(header, state_dir, registry)
            if expect_session is not None and expect_session != session:
                raise StoreError(
                    f"{state_dir}: session identity differs from the expected "
                    "lineage (holo2 has no migration decoders)")
            journal = Journal.resume(state_dir / JOURNAL_NAME, header,
                                     ordering, fsync=fsync)
            sidecar = BlobSidecar.open(state_dir / BLOBS_NAME, fsync=fsync)
            try:
                cached, cache = _open_cache(state_dir, header, registry,
                                            fsync=fsync)
            except CacheError as exc:
                raise StoreError(str(exc)) from exc
            if cached.position > commit_count(ordering):
                raise StoreError(
                    f"{state_dir}: the cache claims {cached.position} "
                    f"commits, the journal records {commit_count(ordering)} — the "
                    "memo cannot know more than the fold; delete the cache "
                    "and it re-derives")
            store = cls(state_dir, session, sidecar, registry,
                        journal=journal, cache=cache,
                        snapshot_every=snapshot_every, fsync=fsync)
            store._adopt(cached.position, cached, skip_close=skip_close)
            return store
        except BaseException:
            if cache is not None:
                cache.close()
            if sidecar is not None:
                sidecar.close()
            if journal is not None:
                journal.close()
            _release_lock(state_dir)
            raise

    @classmethod
    def open_or_create(cls, state_dir: Path, session: Record,
                       registry: RecordRegistry, *,
                       snapshot_every: int = DEFAULT_SNAPSHOT_EVERY,
                       fsync: bool = True,
                       skip_close: bool = False) -> "Store":
        if (state_dir / JOURNAL_NAME).is_file():
            return cls.open(state_dir, registry, snapshot_every=snapshot_every,
                            fsync=fsync, expect_session=session,
                            skip_close=skip_close)
        return cls.create(state_dir, session, registry,
                          snapshot_every=snapshot_every, fsync=fsync)

    def close(self) -> None:
        """Frame whatever the memo still owes, then release the handles."""
        if self._uncached:
            self._frame()
        self._cache.close()
        self._journal.close()
        self._sidecar.close()
        _release_lock(self._dir)

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- identity ----------------------------------------------------------

    @property
    def state_dir(self) -> Path:
        return self._dir

    @property
    def session(self) -> Record:
        return self._session

    @property
    def registry(self) -> RecordRegistry:
        """The record vocabulary this state was written and is read under."""
        return self._registry

    @property
    def commit_seq(self) -> int:
        return self._commit_seq

    @property
    def journal_position(self) -> int:
        """Entries recorded so far — what a replay cursor indexes by."""
        return self._journal_pos

    @property
    def recorded_commits(self) -> int:
        """COMMITS the journal holds, memoised or not (markers excluded)."""
        return commit_count(self._journal.ordering())

    @property
    def trace_path(self) -> Path:
        return self._dir / TRACE_NAME

    def ordering(self) -> tuple[str, ...]:
        """The journal's recorded ordering — what replay consumes.

        Every ENTRY, dispatches included (H4 W2), so it is compared
        against :attr:`journal_position` and never against
        :attr:`commit_seq`. Longer than the position exactly when a crash
        left entries the memo does not cover; the engine re-earns that
        tail.
        """
        return self._journal.ordering()

    def mark_start(self, work_id: WorkId) -> None:
        """Record one DISPATCH, durably, before the fire reads anything.

        The second concurrency ruling's whole mechanism (H4 W2). It folds
        to NOTHING — no record moves, no version bumps, no wake is
        computed, ``commit_seq`` does not advance — because a marker is
        ordering and not a fact (the no-no-op-facts ruling untouched).
        What it buys is the one thing commit order cannot say: WHICH
        state a pooled fire read, which is the fold of the entries before
        this position.

        Main thread, between commits, exactly like the commit append it
        sits beside; and like it, an entry that already stands at this
        position is verified rather than rewritten.
        """
        self._journal.append(start_marker(work_id), self._journal_pos)
        self._journal_pos += 1
        self._outstanding += 1

    def settle_start(self) -> None:
        """One recorded dispatch is over — it committed, or it did not.

        The counterpart of :meth:`mark_start`, and the only thing the
        store does with the pair is decide whether a cache frame may be
        taken here (:meth:`_frame`). A pass that was never marked must
        not decrement, which is why every caller tracks WHICH passes it
        marked rather than calling this for every fire it disarms — the
        live loop by a set of names (``orchestrator._close_dispatch``),
        the replay walk structurally, one mark per pass it is holding
        (``engine.replay._settle_mark``). BOTH halves owe a settle:
        ``mark_start`` counts the dispatch whether the entry it appends
        is new or is a recorded one verified in place, so a walk that
        re-marked and never settled would strand the count above the
        truth for the rest of the run.
        """
        self._outstanding = max(0, self._outstanding - 1)

    @property
    def outstanding_dispatches(self) -> int:
        """Dispatches recorded here that have not settled yet.

        The framing predicate, readable: zero is a clean cut, and at
        quiescence — no fire in flight, live or replayed — zero is also
        the only truthful value. Exposed because "the cadence is still
        armed" is otherwise unobservable from outside, and a leak here
        costs nothing but a memo that silently stops being written.
        """
        return self._outstanding

    # -- reads -------------------------------------------------------------

    def get(self, key: ResourceKey) -> Record | None:
        entry = self._entries.get(key)
        return None if entry is None else entry.record

    def version(self, key: ResourceKey) -> int:
        entry = self._entries.get(key)
        return 0 if entry is None else entry.version

    def keys(self) -> tuple[ResourceKey, ...]:
        return tuple(sorted(self._entries))

    def records(self) -> dict[ResourceKey, Record]:
        return {key: entry.record for key, entry in self._entries.items()}

    def versions(self) -> dict[ResourceKey, int]:
        return {key: entry.version for key, entry in self._entries.items()}

    def subscriptions(self) -> dict[WorkId, ReadSet]:
        return dict(self._subscriptions)

    def subscription(self, worker_id: WorkId) -> ReadSet:
        """One worker's read-set — the row ``subscriptions()`` copies whole.

        The engine reads exactly one worker's row per fire
        (``orchestrator._subscription``) and today pays for a whole-dict
        copy to get it (the audit wart, H4-PLAN W-S). Same thread-safety
        posture as every other read here: a ``dict.get`` off ``_entries``'s
        sibling table, single-threaded by the commit layer (H1's writer
        posture holds until H3).
        """
        return self._subscriptions.get(worker_id, ())

    @property
    def ledger(self) -> SpendLedger:
        return self._ledger

    def close_record(self) -> CloseRecord | None:
        record = self.get(CLOSE_KEY)
        return record if isinstance(record, CloseRecord) else None

    def is_terminal(self) -> bool:
        """A terminal CloseRecord freezes the session (§5.5)."""
        record = self.close_record()
        return record is not None and record.is_terminal

    @property
    def unadmitted_close(self) -> CloseRecord | None:
        """The ``CLOSE_KEY`` record this fold did NOT admit, if there was one.

        The one thing :meth:`_fold_close` says about itself, and it is
        here because both of its drop rules have a consequence outside
        core that only the fold knows about (review fixes, 2026-08-22):

        * a `--no-close` open SET ASIDE a terminal close, and the
          operator is owed that line before the run starts — the skip
          becomes durable (the close SUPERSEDED) the moment this run
          commits anything (``cli.open_receiver``);
        * a close was SUPERSEDED and the journal still holds an
          unmemoised tail, which a CLOSING policy cannot re-earn — it
          would re-decide the close mid-tail (``engine.replay.recover``).

        WHICH rule dropped it is the caller's own flag, not a second
        field: ``skip_close`` returns before the supersede branch is
        reached, so the two can never both fire on one open.
        """
        return self._unadmitted_close

    # -- bulk values -------------------------------------------------------

    def put_array(self, array: np.ndarray) -> BlobRef:
        return self._sidecar.put_array(array)

    def put_staged(self, blob: StagedBlob) -> BlobRef:
        """Materialise a proposal's staged bulk value (R1/M6).

        The staged ref is re-derived by the sidecar from the bytes, so a
        disagreement means the proposal's records reference content that
        is not what it staged — refused loudly rather than stored.
        """
        ref = self._sidecar.put(blob.payload, dtype=blob.ref.dtype,
                                shape=blob.ref.shape)
        if ref != blob.ref:
            raise StoreError(
                f"staged blob {blob.ref.sha256}: sidecar addressed it as "
                f"{ref.sha256} ({ref.dtype}/{ref.shape})")
        return ref

    def read_blob(self, ref: BlobRef, *, verify: bool = False) -> memoryview:
        return self._sidecar.read(ref, verify=verify)

    def read_array(self, ref: BlobRef, *, verify: bool = False) -> np.ndarray:
        return self._sidecar.read_array(ref, verify=verify)

    @property
    def blobs(self) -> BlobSidecar:
        return self._sidecar

    # -- writes (commit layer only) ---------------------------------------

    def apply_committed(self, delta: StoreDelta, batch_id: str) -> None:
        """Apply an adjudicated delta, record it, memo it per the cadence.

        The journal append is the durable act and it happens HERE, at the
        commit, because the ordering is what the fold cannot re-derive.
        The cache frame is not: it rides the cadence, and a commit not yet
        framed is a commit whose result is re-earned by replaying the
        journal tail — which is why a failing append leaves the process's
        two halves agreeing with each other. Nothing else here can fail:
        the delta arrives adjudicated, and the commit layer has already
        published the derived views from it (the publication-order law).
        """
        for key, record, version in delta.writes:
            self._entries[key] = _Entry(record, version)
            self._dirty.setdefault(key, None)
        for spend in delta.spends:
            self._ledger.record(spend)
            self._dirty_spends.add((spend.worker_id, spend.route))
        for worker_id, keys in delta.subscriptions:
            if keys:
                self._subscriptions[worker_id] = keys
            else:
                self._subscriptions.pop(worker_id, None)
            self._dirty_subs.add(worker_id)
        self._journal.append(batch_id, self._journal_pos)
        self._journal_pos += 1
        self._commit_seq += 1
        self._uncached += 1
        if self._uncached >= self._snapshot_every and not self._outstanding:
            self._frame()

    # -- the durable state, as one value -----------------------------------

    def state_json(self) -> dict[str, Any]:
        """The whole durable state, canonically ordered.

        Not a file — the cache is append-only frames, and two runs that
        reach the same state legitimately hold different frame boundaries.
        This is the STATE as a value, which is what the gates compare:
        batching invariance, replay fidelity and resume idempotence are
        all "the same state", never "the same bytes on disk". The
        subscription table is here even though the cache derives it: this
        is the state the store HANDS BACK, and a comparison that quietly
        skipped a table its readers can see would be the weaker claim.
        """
        return {
            **starting_point(self._session, self._registry),
            "commit_seq": self._commit_seq,
            "records": [
                {
                    "key": key.to_json(),
                    "version": self._entries[key].version,
                    **encode_typed_record(self._entries[key].record),
                }
                for key in sorted(self._entries)
            ],
            "spends": [encode_dataclass(spend)
                       for spend in self._ledger.entries()],
            "subscriptions": [
                {"worker_id": worker_id.to_json(),
                 "read_set": [key.to_json()
                              for key in self._subscriptions[worker_id]]}
                for worker_id in sorted(self._subscriptions)
            ],
        }

    def state_bytes(self) -> bytes:
        return canonical_json_bytes(self.state_json())

    # -- internals ---------------------------------------------------------

    def _frame(self) -> None:
        """Append one delta frame: what moved since the last one.

        **A FRAME IS A RESUME POINT** (H4 W2), which is why the cadence
        above also asks whether any dispatch is outstanding. The memo
        covers COMMITS; the journal now numbers dispatches beside them;
        and a fire dispatched before this commit but landing after it
        would leave its marker BEHIND the resume point and its commit
        AHEAD of it — a boundary no replay can honour, because that pass
        read a store this memo has already moved past. Framing only at a
        clean cut is what keeps "resume from the memo" and "re-earn the
        tail exactly" the same statement.

        The price is honest and is the cache doctrine's own: a saturated
        pool reaches few clean cuts, so its memo lags and a crash
        re-earns a longer tail. The memo is disposable and the journal is
        authoritative — a frame that could not be resumed from would be
        worth less than no frame at all. A serial run is unaffected: the
        pass that just committed is the only one there was.
        """
        self._cache.append(
            self._commit_seq,
            [(key, self._entries[key].record, self._entries[key].version)
             for key in self._dirty],   # FIRST-WRITE order (tilemap ch.8)
            [held for held in (self._ledger.held(worker_id, route)
                               for worker_id, route in sorted(
                                   self._dirty_spends))
             if held is not None],
            self._subscription_residue())
        self._dirty.clear()
        self._dirty_spends.clear()
        self._dirty_subs.clear()
        self._uncached = 0

    def _subscription_residue(self,
                              ) -> list[tuple[WorkId, ReadSet | None]]:
        """What the ledger does NOT explain about the read-sets it derives.

        One row per worker whose subscription or spend moved: the read-set
        itself when the two disagree, and ``None`` — "the derived one
        stands" — when they agree. The row is emitted either way because
        that makes the encoding self-correcting under last-wins: a worker
        that parks on a decline and later fires cancels its own override
        without anything tracking that it had one.

        Measured: on a real sheet every row is ``None`` (2,251 workers,
        zero disagreements), so the 143 MB of duplicated read-sets in the
        old envelope becomes a few tens of KB of "nothing to say".
        """
        derived = spend_read_sets(self._ledger.entries())
        return [
            (worker_id, None if held == derived.get(worker_id, ()) else held)
            for worker_id, held in (
                (worker_id, self._subscriptions.get(worker_id, ()))
                for worker_id in sorted(
                    self._dirty_subs
                    | {worker_id for worker_id, _route in self._dirty_spends}))
        ]

    def _adopt(self, position: int, cached: CachedState, *,
               skip_close: bool = False) -> None:
        """Take the memo as the state, and derive what was not stored.

        THE ONE FOLD SITE into the live table. The journal holds no
        records — it is the starting point and the ordering — so a
        journal TAIL past the memo is re-earned by re-running the work
        (``engine.replay.recover``), which is where the close policy's
        other half lives: a run that never consults in a deciding mode
        never re-earns a close.
        """
        self._entries = {key: _Entry(record, version)
                         for key, (record, version) in cached.records.items()}
        self._fold_close(cached.close_position, skip_close=skip_close)
        self._ledger = SpendLedger.restored(cached.spends)
        self._subscriptions = dict(spend_read_sets(cached.spends))
        for worker_id, keys in cached.subscriptions.items():
            if keys is None:
                continue                      # the derived read-set stands
            elif keys:
                self._subscriptions[worker_id] = keys
            else:
                self._subscriptions.pop(worker_id, None)
        self._commit_seq = position
        self._outstanding = 0
        # The memo counts COMMITS; the journal numbers ENTRIES. Where the
        # tail begins is therefore "just past the last covered commit",
        # which is not the same integer once dispatches are recorded.
        self._journal_pos = position_after_commits(
            self._journal.ordering(), position)
        self._uncached = 0
        self._require_blobs_present()

    def _fold_close(self, close_position: int | None, *,
                    skip_close: bool) -> None:
        """What the live table takes from a recorded close (2026-08-22).

        Two rules, one site, stated in full in the module docstring:
        *a close is terminal only while it is the last word* (superseded
        closes are dropped under EVERY policy), and ``skip_close`` drops
        it outright. Neither touches the journal or the frames — the
        record stays exactly where it was written, which is what makes
        this a read-time policy and not a rewrite.

        The ``integrity_failure`` exception is not symmetry for its own
        sake. A verified or unsupported close is a pure derivation from
        the certificate set, so dropping it loses nothing a later close
        cannot recompute. A conflict's record is not: the conflicting
        write was REFUSED AT THE WALL and never became durable
        (``commit`` rule 1's sibling — nothing fallible runs after
        durable apply), so this record's ``reason`` is the only surviving
        trace of the event (F-11). It refuses instead. It cannot be
        superseded either — the wall refused every commit after it, so no
        later commit can exist — and the rule is stated rather than
        merely true, because the next reader should not have to re-derive
        it from the wall.

        Whatever is dropped is REMEMBERED for this open, in
        :attr:`unadmitted_close` — the fold is the only place that knows
        a record was set aside, and two callers outside core need to say
        so (the operator notice and the recovery refusal).
        """
        self._unadmitted_close = None
        entry = self._entries.get(CLOSE_KEY)
        if entry is None:
            return
        record = entry.record
        integrity = (isinstance(record, CloseRecord)
                     and record.status is CloseStatus.INTEGRITY_FAILURE)
        if skip_close:
            if integrity:
                raise StoreError(
                    f"{self._dir}: this session's close is an INTEGRITY "
                    "FAILURE and --no-close will not skip it. That record "
                    "is the only durable trace of the refused conflicting "
                    "write (F-11) — the wall never made the contradiction "
                    "durable — so it is not a derivation a later close "
                    "recomputes. Re-run without --no-close and the record "
                    "is read and reported exactly as it always was; a "
                    "sheet you mean to decode again from the scans needs a "
                    f"fresh state directory. Reason: {record.reason}")
            del self._entries[CLOSE_KEY]
            self._unadmitted_close = (record if isinstance(record, CloseRecord)
                                      else None)
            return
        if integrity:
            return                     # never superseded, by the same rule
        if not (isinstance(record, CloseRecord) and record.is_terminal):
            return
        if close_position is None:
            return
        if close_position < commit_count(self._journal.ordering()):
            # Commits landed after it: this close is SUPERSEDED, the
            # session is OPEN, and the next closing run recomputes it.
            del self._entries[CLOSE_KEY]
            self._unadmitted_close = record

    def _require_blobs_present(self) -> None:
        """Every referenced bulk value is here — and WHO named a missing one.

        The one load-path check rider r1 does NOT delete, because it is
        not the store auditing its own memo: it is the F-13 residue, a
        statement about the SIDECAR beside it, and the open path is the
        one place naming the citing record is free. The verdict it states
        is the cache doctrine's — a state missing a blob is INCOMPLETE,
        not corrupt, and the remedy for a cache is re-derivation.
        """
        missing = sorted(
            ((ref.sha256, key) for key, entry in self._entries.items()
             for ref in blob_refs(entry.record)
             if not self._sidecar.contains(ref.sha256)),
            key=lambda pair: pair[0])
        if missing:
            sha256, key = missing[0]
            raise StoreError(
                f"{self._dir}: the cache references {len(missing)} blob(s) "
                f"absent from the sidecar, first {sha256} (named by {key}); "
                "this state is INCOMPLETE, not corrupt — the sidecar is a "
                "cache, so the remedy is to decode again from the scans")


def starting_point(session: Record, registry: RecordRegistry) -> dict[str, Any]:
    """The fold's left endpoint: what this session was started AS.

    Written as journal line 1 and as the cache's header frame, compared by
    value on both sides at open. The format row id, the receiver policy,
    the recipe entries, the ordered provider ids and the page domain are
    all inside ``session`` — the identity law binds them by value, and
    core, generic over its registry's session family, does not name a
    field of a record it cannot type.
    """
    return {
        "magic": JOURNAL_MAGIC,
        "schema_version": SCHEMA_VERSION,
        "families": registry.manifest_json(),
        "session_type": registry.session_family.name,
        "session": encode_dataclass(session),
    }


def _open_cache(state_dir: Path, header: Mapping[str, Any],
                registry: RecordRegistry, *, fsync: bool,
                ) -> tuple[CachedState, CacheWriter]:
    """The memo, or the empty one a DELETED memo is.

    Every refusal in this module offers the same remedy — delete the
    cache and the fold re-derives the state — so a missing cache is not
    an error here: it is a state that covers no commits, whose whole
    journal is therefore a tail, which the engine re-earns commit by
    commit. That is what makes the remedy true rather than a figure of
    speech (and it is the only honest reading of a file the doctrine
    calls disposable).
    """
    path = state_dir / CACHE_NAME
    if not path.is_file():
        return (CachedState(0, {}, (), {}, Interner(), 0),
                CacheWriter.create(path, header, fsync=fsync))
    cached = CacheReader.load(path, header, registry)
    return cached, CacheWriter.resume(path, cached, fsync=fsync)


def _fsync_dir(state_dir: Path) -> None:
    dir_fd = os.open(state_dir, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _refuse_legacy(state_dir: Path) -> None:
    """An old state directory refuses by NAME, and is never migrated."""
    if (state_dir / LEGACY_ENVELOPE_NAME).is_file():
        raise StoreError(
            f"{state_dir}: holds a pre-F-16 {LEGACY_ENVELOPE_NAME} envelope "
            f"(schema < {SCHEMA_VERSION}); the state-directory layout is now "
            f"a {JOURNAL_NAME} beside a {CACHE_NAME}, and holo2 has no "
            "migration decoders — decode again from the scans")


def _require_starting_point(header: Any, state_dir: Path,
                            registry: RecordRegistry) -> Record:
    if not isinstance(header, dict):
        raise StoreError(f"{state_dir}: the starting point is not an object")
    if header.get("magic") != JOURNAL_MAGIC:
        raise StoreError(f"{state_dir}: not a holo2 journal")
    version = header.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise StoreError(f"{state_dir}: schema_version must be an integer")
    if version != SCHEMA_VERSION:
        raise StoreError(
            f"{state_dir}: state schema version {version} != "
            f"{SCHEMA_VERSION} (holo2 has no migration decoders)")
    unknown = sorted(set(header) - _STARTING_POINT_FIELDS)
    if unknown:
        raise StoreError(f"{state_dir}: unknown starting-point field(s) {unknown}")
    missing = sorted(_STARTING_POINT_FIELDS - set(header))
    if missing:
        raise StoreError(f"{state_dir}: missing starting-point field(s) {missing}")
    if not isinstance(header["families"], list):
        raise StoreError(f"{state_dir}: the family manifest must be an array")
    _require_manifest(header["families"], registry, state_dir)
    session_family = registry.session_family
    if header["session_type"] != session_family.name:
        raise StoreError(
            f"{state_dir}: session identity is {header['session_type']!r}, "
            f"this build's is {session_family.name!r}")
    try:
        session = decode_dataclass(session_family.record_type,
                                   header["session"])
    except (CodecError, ValueError) as exc:
        raise StoreError(f"{state_dir}: bad session identity: {exc}") from exc
    return session


def _require_manifest(raw: list[Any], registry: RecordRegistry,
                      state_dir: Path) -> None:
    """The R3 schema gate: the state's families must be this build's.

    Refuses BY NAME, because "some schema moved" is not actionable and
    "RegionRecord v1 here, v2 in this build" is: it says which subsystem
    changed its records, which is the whole point of making the schema
    identity a manifest instead of one global integer.
    """
    stored: dict[str, Any] = {}
    for entry in raw:
        if (not isinstance(entry, list) or len(entry) != 2
                or not isinstance(entry[0], str)
                or not isinstance(entry[1], int) or isinstance(entry[1], bool)):
            raise StoreError(
                f"{state_dir}: malformed record-family manifest entry "
                f"{entry!r}")
        stored[entry[0]] = entry[1]
    current = dict(registry.manifest())
    problems: list[str] = []
    for name in sorted(set(stored) | set(current)):
        if name not in current:
            problems.append(
                f"{name} v{stored[name]}: this build registers no such family")
        elif name not in stored:
            problems.append(
                f"{name}: this build registers v{current[name]}, the state "
                "has no such family")
        elif stored[name] != current[name]:
            problems.append(
                f"{name}: state v{stored[name]} != build v{current[name]}")
    if problems:
        raise StoreError(
            f"{state_dir}: record-family manifest mismatch (holo2 has no "
            "migration decoders — re-decode from the captures): "
            + "; ".join(problems))

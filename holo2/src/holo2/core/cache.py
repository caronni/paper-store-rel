"""The cache: the fold's memo — append-only, disposable, never rewritten.

The journal says where the fold started and in what order it committed;
this file remembers what the fold PRODUCED, so a resumed session does not
have to re-earn a sheet it already decoded. It is a memo and nothing
more: **a disposable cache has exactly two honest states, trusted or
re-folded** (F-16 rider r1), which is why the load path below validates
no record it reads. Checking one's own memo is guarding against oneself;
if the memo is wrong the fold is the remedy, not a repair.

Wire shape: a header frame, then one DELTA frame per snapshot cadence and
one at close. Each frame is an 8-byte big-endian length followed by
canonical JSON::

    {"pos": 512,                       journal entries this frame covers
     "keys": [[7, ["tile","0","0","K"]], …],      newly interned keys
     "records": [[7, 3, "TileRecord", {…}], …],   new/changed since the last
     "spends": [[[fam, 7, route, arm, prof], route, [[7,3],…], out, 4, 0], …],
     "subs": [[[fam, 7, route, arm, prof], null], …]}   the derived residue

Whole-file rewrite is ABOLISHED — that is the whole point. The measured
envelope it replaces was 476 MB on one real sheet (6.6 MB of facts, and
the rest the same read-set keys written out twice, once per spend row and
once per subscription), rewritten every 512 commits.

**Interning ids are FILE-LOCAL WIRE ENCODING, never identity.** An id is
an integer this file assigns in first-use order; change the cadence and
the same session interns the same keys under different integers. The
VALUES stay the identity (the hash-free identity law): the key parts are
carried in full, once, and a reader that needs a key reads the parts.
Nothing outside this file may hold, store or compare an intern id.

**Subscriptions are DERIVED, not stored** (F-16 rider). A fired worker's
read-set IS the key set of its spend row's attempt identity — one read of
one worker's keys becomes both, in one commit (``orchestrator._propose``)
— and the same keys written twice were 143 MB of the old envelope. So the
load rebuilds the table from the ledger. MEASURED on a real sheet before
this was built: 2,251 spend rows, 2,251 subscriptions, identical worker
sets, identical key sets, one route per worker, zero differences.

One writer in the tree does NOT pair them, and this file carries the
residue rather than papering over it: a re-offerable DECLINE parks a
descriptor on the keys that would change the provider's mind
(``orchestrator._offer`` → ``_sleep``), which is a subscription with no
attempt behind it — nothing was tried, so nothing was spent. Every frame
therefore carries one row per worker whose subscription or spend moved,
holding the read-set when the ledger does not explain it and ``null``
when it does. On the measured sheet every row is ``null`` (~40 bytes,
against megabytes of read-set), and the exception stays exact instead of
silently lost on the next reopen.

A torn tail (a crash mid-append) is truncated away at load rather than
refused: the frames before it are a valid prefix of the fold, and the
journal's tail past that prefix is re-earned by replay.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Iterable, Mapping, Sequence

from .codec import (CodecError, canonical_json_bytes, decode_dataclass,
                    encode_typed_record, parse_json_bytes)
from .identity import SpendRecord
from .keys import Record, ResourceKey, WorkId, WorkScope
from .records import CLOSE_KEY
from .registry import RecordRegistry

CACHE_NAME = "cache"

#: One 64-bit big-endian length per frame (the all-BE doctrine). A frame
#: is read by seeking exactly this far, so the file needs no delimiter,
#: no escaping and no scan.
_LENGTH_BYTES = 8


class CacheError(RuntimeError):
    """The cache is not this session's, or not readable as frames."""


@dataclass
class Interner:
    """Key <-> file-local integer, assigned in first-use order.

    Public only so the store can hand back an EMPTY one for a cache that
    is not there (a deleted memo is a memo of nothing). Its ids are wire
    encoding; see the module docstring.
    """

    ids: dict[ResourceKey, int] = field(default_factory=dict)
    keys: dict[int, ResourceKey] = field(default_factory=dict)

    def intern(self, key: ResourceKey, fresh: list[tuple[int, ResourceKey]],
               ) -> int:
        held = self.ids.get(key)
        if held is not None:
            return held
        assigned = len(self.ids)
        self.ids[key] = assigned
        self.keys[assigned] = key
        fresh.append((assigned, key))
        return assigned

    def adopt(self, identifier: int, key: ResourceKey) -> None:
        """Take an id a frame already assigned (the ids ARE the file's)."""
        self.ids[key] = identifier
        self.keys[identifier] = key

    def key(self, identifier: Any) -> ResourceKey:
        try:
            return self.keys[identifier]
        except (KeyError, TypeError):
            raise CacheError(f"frame names unknown intern id {identifier!r}")


@dataclass(frozen=True)
class CachedState:
    """What a load recovered: the fold's memo, as far as it was written."""

    position: int
    records: dict[ResourceKey, tuple[Record, int]]
    spends: tuple[SpendRecord, ...]
    #: Read-sets the ledger does not explain (see the module docstring);
    #: ``None`` means "the derived one stands", ``()`` means unsubscribed.
    subscriptions: dict[WorkId, tuple[ResourceKey, ...] | None]
    interner: Interner
    end: int
    """Byte offset one past the last COMPLETE frame (a torn tail is dropped)."""
    close_position: int | None = None
    """The frame position at which ``CLOSE_KEY`` was last written, if ever.

    The ONE thing the memo says about a record beyond its value, and it
    is here because the superseded-close rule needs it (the user's
    `--no-close` ruling, 2026-08-22; ``store._fold_close``): *a close is
    terminal only while it is the last word*. A frame carries the COMMIT
    it covers, so this is an upper bound on the commit that wrote the
    close — which is exactly the direction the rule needs, since a
    commit recorded past it is a commit that landed after the close.
    Frames are last-wins, so a later frame naming the key moves this
    forward with the record it carries.

    **The named key is the price, and it was weighed** (review fix,
    2026-08-22). The key-agnostic shape — a ``{key: last position}`` dict
    the store queries for whichever key it cares about — drops this
    file's one import of a production record identity, and it costs one
    dict entry per DISTINCT key a fold touches, which on a real sheet is
    one per certified tile (thousands) instead of one integer. The memo's
    whole reason for existing is that it does not carry the same key
    twice, so the coupling is the cheaper trade and it is stated here
    rather than left as an inconsistency with the paragraph above."""


def _require_header(read: Any, expected: Mapping[str, Any], path: Path) -> None:
    """The cache GATE, and the whole of it (rider r1).

    Schema version and session identity, compared BY VALUE against the
    journal's own starting point — the cache is a memo OF a fold, so the
    only question worth asking is whether it is a memo of THIS one. Its
    third clause, journal-position sanity, is the caller's: it needs the
    journal's length.
    """
    if read != expected:
        held = read if isinstance(read, dict) else {}
        differing = sorted(name for name in set(held) | set(expected)
                           if held.get(name) != expected.get(name))
        raise CacheError(
            f"{path}: this cache memoises a different session than the "
            f"journal beside it (differs in {differing}); delete it and the "
            "fold re-derives the state")


class CacheReader:
    """Reads frames back, last-wins per key. Validates nothing it reads."""

    @staticmethod
    def load(path: Path, header: Mapping[str, Any],
             registry: RecordRegistry) -> CachedState:
        """Fold the frames into one state — trusted, whole, unchecked.

        Sequential and last-wins: a later frame's record supersedes an
        earlier one's at the same key, which is what makes the delta
        encoding lossless without any rewrite. Decoding a record runs its
        ``__post_init__`` (a frozen dataclass cannot be built any other
        way) and that is the ONLY check on this path: the registry's
        validators and transition rules ran at the commit wall, which is
        the unique place unlawfulness is catchable, and re-running them
        here would be the store auditing its own memo.
        """
        raw = path.read_bytes()
        frames, end = _frames(raw, path)
        if not frames:
            raise CacheError(f"{path}: cache holds no starting point")
        _require_header(frames[0], dict(header), path)
        interner = Interner()
        records: dict[ResourceKey, tuple[Record, int]] = {}
        spends: dict[tuple[WorkId, str], SpendRecord] = {}
        subscriptions: dict[WorkId, tuple[ResourceKey, ...] | None] = {}
        position = 0
        close_position: int | None = None
        for frame in frames[1:]:
            position = _int(frame.get("pos"), path)
            # A frame that will not decode is a BROKEN MEMO, which is the
            # one thing this module has an answer for: it is refused as a
            # cache (delete it, re-fold), never repaired and never
            # partially adopted.
            try:
                for identifier, parts in frame.get("keys", ()):
                    interner.adopt(identifier, ResourceKey.from_json(parts))
                for identifier, version, name, value in frame.get("records", ()):
                    key = interner.key(identifier)
                    records[key] = (
                        _decode_record(name, value, registry, path), version)
                    if key == CLOSE_KEY:
                        close_position = position
                for row in frame.get("spends", ()):
                    spend = _decode_spend(row, interner)
                    spends[(spend.worker_id, spend.route)] = spend
                for worker, keys in frame.get("subs", ()):
                    subscriptions[_decode_worker(worker, interner)] = (
                        None if keys is None
                        else tuple(interner.key(item) for item in keys))
            except (CacheError, CodecError, TypeError, ValueError) as exc:
                raise CacheError(
                    f"{path}: unreadable frame at commit {position}: {exc}; "
                    "delete the cache and the fold re-derives") from exc
        return CachedState(position, records, tuple(spends.values()),
                           subscriptions, interner, end, close_position)


def _frames(raw: bytes, path: Path) -> tuple[list[Any], int]:
    """Every COMPLETE frame, and where the last one ends.

    A short length prefix or a short body is a crash mid-append: the
    frames before it are a valid prefix of the fold and the rest is torn
    bytes, so the read stops and the caller truncates.
    """
    frames: list[Any] = []
    offset = 0
    while offset + _LENGTH_BYTES <= len(raw):
        length = int.from_bytes(raw[offset:offset + _LENGTH_BYTES], "big")
        start = offset + _LENGTH_BYTES
        if start + length > len(raw):
            break
        try:
            frames.append(parse_json_bytes(raw[start:start + length]))
        except CodecError as exc:
            raise CacheError(f"{path}: unreadable frame at {offset}: {exc}") from exc
        offset = start + length
    return frames, offset


def _int(value: Any, path: Path) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CacheError(f"{path}: frame position is {value!r}")
    return value


def _decode_record(name: str, value: Any, registry: RecordRegistry,
                   path: Path) -> Record:
    family = registry.family_named(name)
    if family is None:
        raise CacheError(
            f"{path}: the memo holds a {name!r}, which this build "
            "registers no family for")
    return decode_dataclass(family.record_type, value)


def _decode_worker(row: Any, interner: Interner) -> WorkId:
    family, subject, route, arm, profile = row
    return WorkId(family, interner.key(subject), route, WorkScope(arm, profile))


def _decode_spend(row: Any, interner: Interner) -> SpendRecord:
    worker, route, identity, outcome, attempts, exposures = row
    return SpendRecord(
        worker_id=_decode_worker(worker, interner), route=route,
        identity=tuple((interner.key(item[0]), item[1]) for item in identity),
        outcome=outcome, attempts=attempts, exposures=exposures)


class CacheWriter:
    """Appends delta frames. The handle stays open for the session."""

    def __init__(self, path: Path, handle: IO[bytes], interner: Interner, *,
                 fsync: bool = True) -> None:
        self._path = path
        self._handle = handle
        self._interner = interner
        self._fsync = fsync

    @classmethod
    def create(cls, path: Path, header: Mapping[str, Any], *,
               fsync: bool = True) -> "CacheWriter":
        writer = cls(path, open(path, "xb"), Interner(), fsync=fsync)
        writer._append(dict(header))
        return writer

    @classmethod
    def resume(cls, path: Path, state: CachedState, *,
               fsync: bool = True) -> "CacheWriter":
        """Continue an already-loaded cache, torn tail truncated away."""
        os.truncate(path, state.end)
        return cls(path, open(path, "ab"), state.interner, fsync=fsync)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, position: int,
               records: Sequence[tuple[ResourceKey, Record, int]],
               spends: Iterable[SpendRecord],
               subscriptions: Iterable[
                   tuple[WorkId, tuple[ResourceKey, ...] | None]]) -> None:
        """One delta frame: what changed since the last one, and where."""
        fresh: list[tuple[int, ResourceKey]] = []
        rows = [[self._interner.intern(key, fresh), version,
                 *_typed(record)]
                for key, record, version in records]
        spend_rows = [self._spend_row(spend, fresh) for spend in spends]
        subs = [[self._worker_row(worker, fresh),
                 None if keys is None
                 else [self._interner.intern(key, fresh) for key in keys]]
                for worker, keys in subscriptions]
        self._append({"pos": position,
                      "keys": [[identifier, key.to_json()]
                               for identifier, key in fresh],
                      "records": rows,
                      "spends": spend_rows,
                      "subs": subs})

    def close(self) -> None:
        self._handle.close()

    # -- internals ---------------------------------------------------------

    def _worker_row(self, worker: WorkId,
                    fresh: list[tuple[int, ResourceKey]]) -> list[Any]:
        return [worker.family, self._interner.intern(worker.subject, fresh),
                worker.route, worker.scope.arm, worker.scope.profile]

    def _spend_row(self, spend: SpendRecord,
                   fresh: list[tuple[int, ResourceKey]]) -> list[Any]:
        return [
            self._worker_row(spend.worker_id, fresh),
            spend.route,
            [[self._interner.intern(key, fresh), version]
             for key, version in spend.identity],
            spend.outcome, spend.attempts, spend.exposures,
        ]

    def _append(self, frame: Mapping[str, Any]) -> None:
        payload = canonical_json_bytes(frame)
        self._handle.write(len(payload).to_bytes(_LENGTH_BYTES, "big"))
        self._handle.write(payload)
        self._handle.flush()
        if self._fsync:
            os.fsync(self._handle.fileno())


def _typed(record: Record) -> tuple[str, Any]:
    encoded = encode_typed_record(record)
    return encoded["type"], encoded["value"]


def spend_read_sets(spends: Iterable[SpendRecord],
                    ) -> dict[WorkId, tuple[ResourceKey, ...]]:
    """Subscriptions, DERIVED (F-16 rider): a read-set is its identity's keys.

    The declaration a commit carries and the identity it spends are built
    from one read of one worker's keys (``orchestrator._propose``), so the
    durable subscription table was a second copy of what the ledger holds.
    An empty read-set is not a subscription (the store drops those on
    write), so it is not one here either. What this cannot explain — a
    parked decline, which subscribes without attempting — rides the frame
    as an override; see the module docstring.
    """
    derived: dict[WorkId, tuple[ResourceKey, ...]] = {}
    for spend in spends:
        keys = tuple(key for key, _version in spend.identity)
        if keys:
            derived[spend.worker_id] = keys
    return derived


__all__ = ["CACHE_NAME", "CacheError", "CacheReader", "CacheWriter",
           "CachedState", "Interner", "spend_read_sets"]

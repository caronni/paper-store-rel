"""Scheduler instrumentation for ONE costly measurement run.

DEFAULT OFF.  `HOLO3_SCHED_TRACE=1` in the environment arms it at
`_start`; anything else leaves `TRACE` the null object and the engine's
hot paths guarded by a single boolean attribute (`_Engine._trace_on`).

MEASUREMENT ONLY.  Nothing here is read by a scheduling decision: no
price, stage, eligibility, retire, wake or fold consults the trace, and
the redundancy digest of §5 is RECORDED AND NEVER ACTED ON (the job
still runs).  The trace writes its own files under
`<run_dir>/sched-trace/` and appends NOTHING to the event list, so a
traced run's `events.jsonl`, `report.json`, panes, snapshot and payload
are byte-identical to an untraced one.

What it answers (the five static-analysis lenses' wishlists, 2026-09-17):

* the wake fan-out matrix — (key kind) x (woken plugin) — against the
  engine's one global `_wakes` integer;
* the push funnel and the pop funnel, per plugin, split by outcome:
  today `_stale_skips` merges the seat-sequence skip and the version
  floor and the other eight causes are invisible;
* main-thread wall clock by EXCLUSIVE category (fold / births / touch /
  push / fill / merge / close / wait / stat / other) plus per-plugin,
  per-callback INCLUSIVE time and call counts for stage, cost,
  eligible, retire, prepare, reads and subjects_of;
* per fire: wall duration beside `cpu_s` (which is `thread_time` and
  hides every stall), the wakes and wake kinds since that worker's last
  fire, and whether the decode input repeats one already fired;
* a per-bookmark ledger and a timeline, so "queued 8,499, fired 0" and
  "36 WindowScheduled for one window" stop being end-state numbers.

THREADING: every hook site runs on the engine's own thread (the merge
thread).  `prepare` — where the digests are taken — is called from
`_fill` on that thread; job closures run on workers and touch nothing
here.  `TRACE` is a module global because the plugin-side digest hooks
must reach it without a store accessor; one run at a time is the
contract (the test harness serialises decodes under its work lock).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .sched_trace_folds import FoldRecorder, NullFolds

__all__ = ["TRACE", "NullTrace", "SchedTrace", "arm", "disarm",
           "enabled_by_env"]

ENV_ENABLE = "HOLO3_SCHED_TRACE"
ENV_EVERY_S = "HOLO3_SCHED_TRACE_EVERY_S"
DEFAULT_EVERY_S = 300.0
DIR_NAME = "sched-trace"
SCHEMA = 1

TIMELINE_EVERY_S = 2.0

#: `_push_worker`'s six exits, in the order the function tests them.
PUSH_OUTCOMES: tuple[str, ...] = (
    "inflight_pending", "retire_at_push", "stage_none", "seat_stands",
    "reseat_price", "first_seat")

#: `_fill`'s ten exits.  `stale_seq` and `version_floor` share one
#: counter in the shipped engine (`_stale_skips`) and mean opposite
#: things; everything below `retire_at_pop` is invisible today.
POP_CAUSES: tuple[str, ...] = (
    "stale_seq", "retired", "inflight_pending", "retire_at_pop",
    "version_floor", "not_eligible", "stage_none", "cost_repush",
    "prepare_none", "fired")

CALLBACKS: tuple[str, ...] = (
    "stage", "cost", "eligible", "retire", "prepare", "reads",
    "subjects_of")

#: EXCLUSIVE main-thread categories: a nested region charges its own
#: bucket and its parent pays only the time outside it, so the totals
#: sum to the traced wall.
CATEGORIES: tuple[str, ...] = (
    "fold", "births", "touch", "push", "fill", "merge", "close", "wait",
    "stat", "operator", "intake", "snapshot", "other")


def enabled_by_env(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return env.get(ENV_ENABLE, "").strip() not in ("", "0", "no", "off")


def every_s_by_env(environ: dict[str, str] | None = None) -> float:
    env = os.environ if environ is None else environ
    raw = env.get(ENV_EVERY_S, "").strip()
    if not raw:
        return DEFAULT_EVERY_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_EVERY_S
    return value if value > 0 else DEFAULT_EVERY_S


# ---------------------------------------------------------------- digests


def _blob(part: Any) -> bytes:
    """Canonical bytes for one digest part.

    numpy arrays go in as their own buffer plus dtype and shape (a
    float32 patch and its float64 twin are different inputs); everything
    else goes in as its repr, which is stable for the tuples of ints and
    strings the callers pass.
    """
    buffer = getattr(part, "tobytes", None)
    if buffer is not None and hasattr(part, "dtype"):
        return (f"{part.dtype.str}{part.shape}".encode() + buffer())
    return repr(part).encode()


def digest_of(kind: str, parts: tuple[Any, ...]) -> str:
    hasher = hashlib.blake2b(digest_size=16)
    hasher.update(kind.encode())
    for part in parts:
        hasher.update(b"\x1e")
        hasher.update(_blob(part))
    return hasher.hexdigest()


# ------------------------------------------------------------- the ledger


@dataclass(slots=True)
class _Book:
    """One bookmark's whole life, kept in memory only while tracing."""

    plugin: str
    subject: str
    births: int = 0
    rebirths: int = 0
    pushes: dict[str, int] = field(default_factory=dict)
    pops: dict[str, int] = field(default_factory=dict)
    wakes: int = 0
    wake_kinds: dict[str, int] = field(default_factory=dict)
    wakes_since_fire: int = 0
    kinds_since_fire: dict[str, int] = field(default_factory=dict)
    fires: int = 0
    zero_yield_fires: int = 0
    cpu_s: float = 0.0
    zero_yield_cpu_s: float = 0.0
    seats_outstanding: int = 0
    max_seats: int = 0
    first_seat_wall_s: float | None = None
    first_fire_wall_s: float | None = None
    last_fire_wall_s: float | None = None
    retire_cause: str | None = None
    retire_wall_s: float | None = None
    digests: set[str] = field(default_factory=set)
    redundant_fires: int = 0
    redundant_cpu_s: float = 0.0
    certificates: int = 0
    #: the fire ordinal at which this subject's LAST certificate arrived
    last_cert_fire: int = 0


@dataclass(slots=True)
class _Open:
    """A fire between its submit and its merge."""

    seq: int
    stage: str
    cost: int
    attempts: int
    version: int
    tried_version_before: int
    wakes_since_last_fire: int
    wake_kinds_since_last_fire: dict[str, int]
    wall_started_s: float
    digest: str | None
    digest_kind: str | None
    redundant_input: bool | None
    bare: str | None
    reason: str | None


class _Clock:
    """Exclusive main-thread accounting over a category stack."""

    __slots__ = ("totals", "_stack", "_mark")

    def __init__(self) -> None:
        self.totals: dict[str, int] = {name: 0 for name in CATEGORIES}
        self._stack: list[str] = ["other"]
        self._mark = time.perf_counter_ns()

    def enter(self, category: str) -> None:
        now = time.perf_counter_ns()
        self.totals[self._stack[-1]] += now - self._mark
        self._mark = now
        self._stack.append(category)

    def leave(self) -> None:
        now = time.perf_counter_ns()
        self.totals[self._stack[-1]] += now - self._mark
        self._mark = now
        if len(self._stack) > 1:
            self._stack.pop()

    def settle(self) -> None:
        now = time.perf_counter_ns()
        self.totals[self._stack[-1]] += now - self._mark
        self._mark = now


def _runtime() -> dict[str, Any]:
    """The interpreter this run is on.

    A low worker utilisation has two very different explanations -- a
    serialised main thread, or GIL contention among the workers -- and
    `sys._is_gil_enabled()` settles the second one outright.  No
    archived run in this project records it.
    """
    import sys

    gil = getattr(sys, "_is_gil_enabled", None)
    return {"python": sys.version.split()[0], "platform": sys.platform,
            "gil_enabled": None if gil is None else bool(gil()),
            "pid": os.getpid()}


def _rss_mb() -> float:
    """Peak RSS in MB.  `ru_maxrss` is BYTES on darwin, KiB on linux."""
    try:
        import resource
        import sys

        peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:
        return 0.0
    unit = 1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0
    return peak / unit


def _quantile(sorted_values: list[int], q: float) -> int:
    if not sorted_values:
        return 0
    index = min(len(sorted_values) - 1,
                max(0, int(round(q * (len(sorted_values) - 1)))))
    return sorted_values[index]


class NullTrace:
    """What the engine holds when the trace is off.

    The engine calls `enter`/`leave`/`sample` unconditionally from its
    outer loop (of the order of ten turns a second, so a no-op method
    call there is free); every HOT path -- `_push_worker`, `_touch`,
    `_ingest`, `_fill`, the plugins' `note_input` -- checks a boolean
    attribute first and never reaches this object at all.
    """

    __slots__ = ()
    enabled = False
    #: The fold recorder's null twin, so `TRACE.folds` is always a
    #: callable object even when nobody armed anything.
    folds = NullFolds()

    def enter(self, category: str) -> None:
        return None

    def leave(self) -> None:
        return None

    def sample(self, engine: object, force: bool = False) -> None:
        return None

    def due(self) -> bool:
        return False

    def note_input(self, kind: str, parts: tuple[Any, ...],
                   bare_parts: tuple[Any, ...] | None = None) -> None:
        return None

    def note_reason(self, reason: str) -> None:
        return None

    def result_reasons(self, facts: tuple[Any, ...]) -> str | None:
        return None

    def dump(self, engine: object) -> None:
        return None

    def finish(self, engine: object) -> None:
        return None


class SchedTrace:
    """The armed instrument.  One per run; see the module docstring."""

    def __init__(self, out_dir: Path, every_s: float = DEFAULT_EVERY_S,
                 workers: int = 1) -> None:
        self.enabled = True
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.every_s = float(every_s)
        self.workers = int(workers)
        self.started_wall_s = time.monotonic()
        self.clock = _Clock()
        self._books: dict[tuple[str, Any], _Book] = {}
        self._open: dict[tuple[str, Any], _Open] = {}
        self._fan_out: dict[tuple[str, str], int] = {}
        self._callbacks: dict[tuple[str, str], list[float]] = {}
        self._pushes: dict[tuple[str, str], int] = {}
        self._pops: dict[tuple[str, str], int] = {}
        self._fires: dict[str, int] = {}
        self._fire_cpu_s: dict[str, float] = {}
        self._zero_yield: dict[str, int] = {}
        self._zero_yield_cpu_s: dict[str, float] = {}
        self._redundant: dict[str, int] = {}
        self._redundant_cpu_s: dict[str, float] = {}
        self._facts: dict[str, int] = {}
        self._facts_refused: dict[str, int] = {}
        self._reasons: dict[tuple[str, str], int] = {}
        self._digest_calls = 0
        self._digest_ns = 0
        self._digest_kinds: dict[str, int] = {}
        self._wakes = 0
        self._max_frontier = 0
        self._max_index_keys = 0
        self._max_subscriptions = 0
        self._fire_seq = 0
        self._retire_causes: dict[str, int] = {}
        self._pending_digest: tuple[str, str] | None = None
        self._pending_bare: str | None = None
        self._pending_reason: str | None = None
        self._next_timeline_s = 0.0
        self._next_dump_s = self.every_s
        self._dumps = 0
        self._notes: list[str] = []
        self._fires_fh = (self.out_dir / "fires.jsonl").open(
            "a", encoding="utf-8")
        self._timeline_fh = (self.out_dir / "timeline.jsonl").open(
            "a", encoding="utf-8")
        self._ladder_fh = (self.out_dir / "place-ladder.jsonl").open(
            "a", encoding="utf-8")
        #: The fold-time loss record (sched_trace_folds): written by
        #: `store_folds` behind the same single `TRACE.enabled` guard.
        self.folds = FoldRecorder(self.out_dir)

    # ------------------------------------------------------------ clock

    def enter(self, category: str) -> None:
        self.clock.enter(category)

    def leave(self) -> None:
        self.clock.leave()

    def wall_s(self) -> float:
        return time.monotonic() - self.started_wall_s

    # -------------------------------------------------------- callbacks

    def timed(self, kind: str, plugin: str, fn: Any, *args: Any) -> Any:
        """Call one descriptor callback and charge it to (plugin, kind).

        INCLUSIVE: this overlaps the exclusive category totals on
        purpose — a `stage` call inside `_push_worker` is both push time
        and stage time, and the two tables answer different questions.
        """
        started = time.perf_counter_ns()
        try:
            return fn(*args)
        finally:
            # The clock is read FIRST in the epilogue, so the ledger's
            # own bookkeeping (~80 ns) is not charged to the callback
            # (review 2026-09-17, B-1).
            elapsed = float(time.perf_counter_ns() - started)
            row = self._callbacks.get((plugin, kind))
            if row is None:
                self._callbacks[(plugin, kind)] = [1.0, elapsed]
            else:
                row[0] += 1.0
                row[1] += elapsed

    # ------------------------------------------------------- bookmarks

    def _book(self, plugin: str, subject: Any) -> _Book:
        key = (plugin, subject)
        book = self._books.get(key)
        if book is None:
            book = _Book(plugin=plugin, subject=repr(subject))
            self._books[key] = book
        return book

    def birth(self, plugin: str, subject: Any, rebirth: bool) -> None:
        book = self._book(plugin, subject)
        if rebirth:
            book.rebirths += 1
        else:
            book.births += 1

    def wake(self, plugin: str, subject: Any, key_kind: str) -> None:
        self._wakes += 1
        cell = (key_kind, plugin)
        self._fan_out[cell] = self._fan_out.get(cell, 0) + 1
        book = self._book(plugin, subject)
        book.wakes += 1
        book.wake_kinds[key_kind] = book.wake_kinds.get(key_kind, 0) + 1
        book.wakes_since_fire += 1
        book.kinds_since_fire[key_kind] = \
            book.kinds_since_fire.get(key_kind, 0) + 1

    def push(self, plugin: str, subject: Any, outcome: str) -> None:
        cell = (plugin, outcome)
        self._pushes[cell] = self._pushes.get(cell, 0) + 1
        book = self._book(plugin, subject)
        book.pushes[outcome] = book.pushes.get(outcome, 0) + 1

    def seat(self, plugin: str, subject: Any, stage: str, cost: int,
             superseded: bool, frontier_len: int = -1) -> None:
        # The heap's true maximum, taken at every seat rather than at the
        # 2 s timeline sample (review 2026-09-17, B-7).
        if frontier_len > self._max_frontier:
            self._max_frontier = frontier_len
        book = self._book(plugin, subject)
        # A supersede leaves the OLD tuple in the heap to be skipped at
        # its pop (lazy deletion), so both cases add one heap entry and
        # `seats_outstanding` counts the stale ones too -- which is what
        # `max_seats` is for.
        book.seats_outstanding += 1
        if book.seats_outstanding > book.max_seats:
            book.max_seats = book.seats_outstanding
        wall_s = self.wall_s()
        if book.first_seat_wall_s is None:
            book.first_seat_wall_s = wall_s
        if plugin == "place":
            self._ladder_fh.write(json.dumps({
                "kind": "seat", "window": repr(subject), "stage": stage,
                "cost": int(cost), "superseded": bool(superseded),
                "wall_s": round(wall_s, 6)}) + "\n")

    def pop(self, plugin: str, subject: Any, cause: str) -> None:
        cell = (plugin, cause)
        self._pops[cell] = self._pops.get(cell, 0) + 1
        book = self._book(plugin, subject)
        book.pops[cause] = book.pops.get(cause, 0) + 1
        if book.seats_outstanding > 0:
            book.seats_outstanding -= 1

    def retire(self, plugin: str, subject: Any, cause: str) -> None:
        book = self._book(plugin, subject)
        book.retire_cause = cause
        book.retire_wall_s = self.wall_s()
        self._retire_causes[cause] = self._retire_causes.get(cause, 0) + 1
        if plugin == "place":
            self._ladder_fh.write(json.dumps({
                "kind": "retire", "window": repr(subject), "cause": cause,
                "wall_s": round(book.retire_wall_s, 6)}) + "\n")

    # ----------------------------------------------------- input digest

    def clear_input(self) -> None:
        self._pending_digest = None
        self._pending_bare = None
        self._pending_reason = None

    def note_input(self, kind: str, parts: tuple[Any, ...],
                   bare_parts: tuple[Any, ...] | None = None) -> None:
        """Called by a plugin's `prepare` with its ACTUAL decode input.

        Two digests, because two different questions are being asked.
        `input_digest` is over everything the decoder was handed, STAGE
        AND ALL, and answers "has this subject decoded this before".
        `input_digest_bare` is over the evidence alone — the assembled
        cut, without the stage or the pending streams — and is what
        joins a `tiles.retry` at 150 iterations to the `tiles.scan` at
        60 that armed it, a pair the stage-carrying digest can never
        match by construction.

        The digest is attributed to the prepare the engine is inside
        (`clear_input` / `take_input`).  Recording only: the job the
        prepare returns is submitted whatever either digest says.
        """
        started = time.perf_counter_ns()
        self._pending_digest = (kind, digest_of(kind, parts))
        if bare_parts is not None:
            self._pending_bare = digest_of("bare", bare_parts)
        self._digest_calls += 1
        self._digest_kinds[kind] = self._digest_kinds.get(kind, 0) + 1
        self._digest_ns += time.perf_counter_ns() - started

    def note_reason(self, reason: str) -> None:
        self._pending_reason = reason

    #: What a job's own facts SAY, gathered on the merge thread over the
    #: handful of facts one job returns.  Three lenses asked for exactly
    #: this: `refine.color`'s four refusal reasons (which the fold
    #: swallows and no event carries), `place`'s outcome, and the tile
    #: rows' attempt outcome.  Reading only -- the fold is untouched.
    def result_reasons(self, facts: tuple[Any, ...]) -> str | None:
        seen: list[str] = []
        for fact in facts:
            revision = getattr(fact, "revision", None)
            reason = getattr(revision, "reason", None)
            if reason is None:
                reason = getattr(fact, "outcome", None)
            if reason is None:
                reason = getattr(fact, "reason", None)
            if reason is None:
                continue
            text = str(reason)
            if revision is not None:
                adopted = bool(getattr(revision, "adopted", False))
                text = f"{text}/{'adopted' if adopted else 'refused'}"
            if text not in seen:
                seen.append(text)
        return ",".join(seen) if seen else None

    def take_input(self) -> tuple[str | None, str | None, str | None,
                                  str | None]:
        kind_digest = self._pending_digest
        bare = self._pending_bare
        reason = self._pending_reason
        self._pending_digest = None
        self._pending_bare = None
        self._pending_reason = None
        if kind_digest is None:
            return None, None, bare, reason
        return kind_digest[0], kind_digest[1], bare, reason

    # ------------------------------------------------------------ fires

    def fire(self, plugin: str, subject: Any, seq: int, stage: str,
             cost: int, attempts: int, version: int,
             tried_version_before: int) -> None:
        book = self._book(plugin, subject)
        digest_kind, digest, bare, reason = self.take_input()
        redundant: bool | None = None
        if digest is not None:
            redundant = digest in book.digests
            book.digests.add(digest)
        self._open[(plugin, subject)] = _Open(
            seq=seq, stage=stage, cost=int(cost), attempts=int(attempts),
            version=int(version),
            tried_version_before=int(tried_version_before),
            wakes_since_last_fire=book.wakes_since_fire,
            wake_kinds_since_last_fire=dict(book.kinds_since_fire),
            wall_started_s=self.wall_s(), digest=digest,
            digest_kind=digest_kind, redundant_input=redundant,
            bare=bare, reason=reason)
        book.wakes_since_fire = 0
        book.kinds_since_fire = {}

    def fire_done(self, plugin: str, subject: Any, cpu_s: float,
                  n_certificates: int, n_poses: int, n_words: int,
                  n_facts: int = 0, n_facts_refused: int = 0,
                  reason: str | None = None) -> None:
        open_fire = self._open.pop((plugin, subject), None)
        if open_fire is None:
            return
        book = self._book(plugin, subject)
        ended_s = self.wall_s()
        book.fires += 1
        book.cpu_s += float(cpu_s)
        self._fires[plugin] = self._fires.get(plugin, 0) + 1
        self._fire_cpu_s[plugin] = self._fire_cpu_s.get(plugin, 0.0) \
            + float(cpu_s)
        yielded = n_certificates or n_poses or n_words
        if not yielded:
            book.zero_yield_fires += 1
            book.zero_yield_cpu_s += float(cpu_s)
            self._zero_yield[plugin] = self._zero_yield.get(plugin, 0) + 1
            self._zero_yield_cpu_s[plugin] = \
                self._zero_yield_cpu_s.get(plugin, 0.0) + float(cpu_s)
        if n_certificates:
            book.certificates += n_certificates
            book.last_cert_fire = book.fires
        if open_fire.redundant_input:
            book.redundant_fires += 1
            book.redundant_cpu_s += float(cpu_s)
            self._redundant[plugin] = self._redundant.get(plugin, 0) + 1
            self._redundant_cpu_s[plugin] = \
                self._redundant_cpu_s.get(plugin, 0.0) + float(cpu_s)
        self._facts[plugin] = self._facts.get(plugin, 0) + int(n_facts)
        self._facts_refused[plugin] = self._facts_refused.get(plugin, 0) \
            + int(n_facts_refused)
        if reason is not None:
            cell = (plugin, reason)
            self._reasons[cell] = self._reasons.get(cell, 0) + 1
        if book.first_fire_wall_s is None:
            book.first_fire_wall_s = open_fire.wall_started_s
        book.last_fire_wall_s = ended_s
        self._fire_seq += 1
        self._fires_fh.write(json.dumps({
            "fire": self._fire_seq,
            "seq": open_fire.seq,
            "plugin": plugin,
            "subject": repr(subject),
            "stage": open_fire.stage,
            "cost": open_fire.cost,
            "attempts": open_fire.attempts,
            "version_at_fire": open_fire.version,
            "tried_version_before": open_fire.tried_version_before,
            "wakes_since_last_fire": open_fire.wakes_since_last_fire,
            "wake_kinds_since_last_fire":
                open_fire.wake_kinds_since_last_fire,
            "cpu_s": round(float(cpu_s), 6),
            "wall_started_s": round(open_fire.wall_started_s, 6),
            "wall_ended_s": round(ended_s, 6),
            "wall_s": round(ended_s - open_fire.wall_started_s, 6),
            "n_certificates": int(n_certificates),
            "n_poses": int(n_poses),
            "n_words": int(n_words),
            "n_facts": int(n_facts),
            "n_facts_refused": int(n_facts_refused),
            "redundant_input": open_fire.redundant_input,
            "input_digest": open_fire.digest,
            "input_digest_kind": open_fire.digest_kind,
            "input_digest_bare": open_fire.bare,
            "reason": reason or open_fire.reason}) + "\n")
        if plugin == "place":
            self._ladder_fh.write(json.dumps({
                "kind": "fire", "window": repr(subject),
                "stage": open_fire.stage, "cost": open_fire.cost,
                "started_wall_s": round(open_fire.wall_started_s, 6),
                "fire_wall_s": round(ended_s, 6),
                "cpu_s": round(float(cpu_s), 6),
                "n_poses": int(n_poses), "n_words": int(n_words),
                "outcome": ("poses" if n_poses else "none")}) + "\n")

    # --------------------------------------------------------- timeline

    def sample(self, engine: object, force: bool = False) -> None:
        wall_s = self.wall_s()
        if not force and wall_s < self._next_timeline_s:
            return
        self._next_timeline_s = wall_s + TIMELINE_EVERY_S
        frontier = len(getattr(engine, "_frontier", ()))
        if frontier > self._max_frontier:
            self._max_frontier = frontier
        self.clock.settle()
        totals = {name: round(value / 1e9, 6)
                  for name, value in self.clock.totals.items()}
        # Busy = time the loop spent starving its workers: neither the
        # idle wait nor the intake, which runs before any worker exists.
        busy = sum(value for name, value in totals.items()
                   if name not in ("wait", "intake"))
        self._timeline_fh.write(json.dumps({
            "wall_s": round(wall_s, 3),
            "inflight": len(getattr(engine, "_inflight", ())),
            "frontier_len": frontier,
            "queued": {plugin: count for plugin, count
                       in sorted(getattr(engine, "_queued", {}).items())
                       if count},
            "wakes": self._wakes,
            "fires": sum(self._fires.values()),
            "cpu_s": round(sum(self._fire_cpu_s.values()), 3),
            "certificates": len(getattr(engine, "_certificates", ())),
            "bookmarks": len(self._books),
            "main_thread_s": totals,
            "main_thread_busy_s": round(busy, 6),
            "rss_mb": round(_rss_mb(), 1)}) + "\n")

    # ------------------------------------------------------------ dumps

    def due(self) -> bool:
        return self.wall_s() >= self._next_dump_s

    def _subscribers(self, engine: object) -> dict[str, Any]:
        index = getattr(engine, "_index", {})
        sizes: dict[str, list[int]] = {}
        total = 0
        for key, subscribers in index.items():
            kind = str(key[0]) if isinstance(key, tuple) and key else "?"
            size = len(subscribers)
            total += size
            sizes.setdefault(kind, []).append(size)
        if len(index) > self._max_index_keys:
            self._max_index_keys = len(index)
        if total > self._max_subscriptions:
            self._max_subscriptions = total
        out: dict[str, Any] = {}
        for kind, values in sorted(sizes.items()):
            values.sort()
            out[kind] = {
                "keys": len(values), "subscriptions": sum(values),
                "max": values[-1],
                "mean": round(sum(values) / len(values), 3),
                "p99": _quantile(values, 0.99)}
        return {"wall_s": round(self.wall_s(), 3),
                "keys_total": len(index), "subscriptions_total": total,
                "by_key_kind": out}

    def _top_subjects(self, limit: int = 20) -> dict[str, Any]:
        by_plugin: dict[str, list[_Book]] = {}
        for book in self._books.values():
            by_plugin.setdefault(book.plugin, []).append(book)
        out: dict[str, Any] = {}
        for plugin, books in sorted(by_plugin.items()):
            ranked = sorted(books, key=lambda b: (-b.fires, -b.wakes,
                                                  b.subject))[:limit]
            out[plugin] = [{
                "subject": book.subject, "fires": book.fires,
                "wakes": book.wakes, "cpu_s": round(book.cpu_s, 3),
                "zero_yield_fires": book.zero_yield_fires,
                "redundant_fires": book.redundant_fires,
                "certificates": book.certificates,
                "last_cert_fire": book.last_cert_fire,
                "pushes": dict(sorted(book.pushes.items())),
                "pops": dict(sorted(book.pops.items())),
                "retire_cause": book.retire_cause,
            } for book in ranked]
        return out

    def _census(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for book in self._books.values():
            row = out.setdefault(book.plugin, {
                "bookmarks": 0, "fired": 0, "never_fired": 0,
                "retired": 0, "births": 0, "rebirths": 0,
                "wakes": 0, "fires": 0, "cpu_s": 0.0,
                "zero_yield_fires": 0, "zero_yield_cpu_s": 0.0,
                "redundant_fires": 0, "redundant_cpu_s": 0.0,
                "max_seats_one_bookmark": 0,
                "fires_hist": {}, "wakes_per_fire_hist": {},
                "seat_to_first_fire_s": {"n": 0, "sum": 0.0, "max": 0.0}})
            row["bookmarks"] += 1
            row["births"] += book.births
            row["rebirths"] += book.rebirths
            row["wakes"] += book.wakes
            row["fires"] += book.fires
            row["cpu_s"] += book.cpu_s
            row["zero_yield_fires"] += book.zero_yield_fires
            row["zero_yield_cpu_s"] += book.zero_yield_cpu_s
            row["redundant_fires"] += book.redundant_fires
            row["redundant_cpu_s"] += book.redundant_cpu_s
            row["max_seats_one_bookmark"] = max(
                row["max_seats_one_bookmark"], book.max_seats)
            if book.fires:
                row["fired"] += 1
            else:
                row["never_fired"] += 1
            if book.retire_cause is not None:
                row["retired"] += 1
            label = str(book.fires) if book.fires <= 10 else ">10"
            row["fires_hist"][label] = row["fires_hist"].get(label, 0) + 1
            if book.fires:
                per = book.wakes // book.fires
                bucket = ("0" if per == 0 else "1" if per == 1
                          else "2-9" if per < 10 else "10-99" if per < 100
                          else "100-999" if per < 1000 else ">=1000")
                row["wakes_per_fire_hist"][bucket] = \
                    row["wakes_per_fire_hist"].get(bucket, 0) + 1
            if (book.first_seat_wall_s is not None
                    and book.first_fire_wall_s is not None):
                delay = book.first_fire_wall_s - book.first_seat_wall_s
                stat = row["seat_to_first_fire_s"]
                stat["n"] += 1
                stat["sum"] += delay
                stat["max"] = max(stat["max"], delay)
        for row in out.values():
            row["cpu_s"] = round(row["cpu_s"], 3)
            row["zero_yield_cpu_s"] = round(row["zero_yield_cpu_s"], 3)
            row["redundant_cpu_s"] = round(row["redundant_cpu_s"], 3)
            stat = row["seat_to_first_fire_s"]
            stat["mean"] = round(stat["sum"] / stat["n"], 4) if stat["n"] \
                else 0.0
            stat["sum"] = round(stat["sum"], 3)
            stat["max"] = round(stat["max"], 4)
            row["fires_hist"] = dict(sorted(row["fires_hist"].items()))
            row["wakes_per_fire_hist"] = dict(
                sorted(row["wakes_per_fire_hist"].items()))
        return dict(sorted(out.items()))

    def summary(self, engine: object) -> dict[str, Any]:
        self.clock.settle()
        totals = {name: round(value / 1e9, 6)
                  for name, value in self.clock.totals.items()}
        wall_s = self.wall_s()
        cpu_s = sum(self._fire_cpu_s.values())
        subscribers = self._subscribers(engine)
        return {
            "schema": SCHEMA,
            "notes": [
                "measurement only: no scheduling decision reads this file",
                "callback seconds are INCLUSIVE and overlap the exclusive "
                "main_thread_s categories",
                "input digests: tiles.scan/union/retry digest the ASSEMBLED "
                "CUT; tiles.local digests its donor set; tiles.swim "
                "records swim_inputs (covering windows and poses, field "
                "revision, certified neighbourhood labels; since 50a7395e); "
                "refine/refine.color "
                "digest the refinement basis; color digests the lane's "
                "(stage, windows, debt, head fits, field revision, "
                "certificate count) proxy; every other row records null and "
                "its redundancy must be inferred offline from "
                "wakes_since_last_fire and version_at_fire",
                *self._notes],
            "runtime": _runtime(),
            "wall_s": round(wall_s, 3),
            "workers": self.workers,
            "job_cpu_s": round(cpu_s, 3),
            "worker_utilisation": round(
                cpu_s / (wall_s * self.workers), 5) if wall_s else 0.0,
            "wakes": self._wakes,
            "wakes_per_s": round(self._wakes / wall_s, 1) if wall_s else 0.0,
            "fires": sum(self._fires.values()),
            "bookmarks": len(self._books),
            "dumps": self._dumps,
            "main_thread_s": totals,
            "main_thread_busy_s": round(
                sum(v for k, v in totals.items()
                    if k not in ("wait", "intake")), 6),
            "digest": {
                "calls": self._digest_calls,
                "cpu_s": round(self._digest_ns / 1e9, 6),
                "by_kind": dict(sorted(self._digest_kinds.items()))},
            "heap": {
                "frontier_len": len(getattr(engine, "_frontier", ())),
                "max_frontier_len": self._max_frontier,
                "queued": {plugin: count for plugin, count in sorted(
                    getattr(engine, "_queued", {}).items()) if count},
                "index_keys": subscribers["keys_total"],
                "max_index_keys": self._max_index_keys,
                "subscriptions": subscribers["subscriptions_total"],
                "max_subscriptions": self._max_subscriptions,
                "rss_mb": round(_rss_mb(), 1)},
            "by_plugin": {
                "fires": dict(sorted(self._fires.items())),
                "fire_cpu_s": {k: round(v, 3) for k, v
                               in sorted(self._fire_cpu_s.items())},
                "zero_yield_fires": dict(sorted(self._zero_yield.items())),
                "zero_yield_cpu_s": {k: round(v, 3) for k, v
                                     in sorted(
                                         self._zero_yield_cpu_s.items())},
                "redundant_fires": dict(sorted(self._redundant.items())),
                "redundant_cpu_s": {k: round(v, 3) for k, v
                                    in sorted(
                                        self._redundant_cpu_s.items())},
                "facts": dict(sorted(self._facts.items())),
                "facts_refused": dict(sorted(self._facts_refused.items()))},
            "reasons": _two_key(self._reasons),
            "pushes": _two_key(self._pushes),
            "pops": _two_key(self._pops),
            "callbacks": {
                plugin: {kind: {"calls": int(row[0]),
                                "cpu_s": round(row[1] / 1e9, 6)}
                         for (other, kind), row
                         in sorted(self._callbacks.items())
                         if other == plugin}
                for plugin in sorted({key[0] for key
                                      in self._callbacks})},
            "fan_out": _fan_out_table(self._fan_out),
            "retire_causes": dict(sorted(self._retire_causes.items())),
            "census": self._census(),
            "subscribers": subscribers,
            "top_subjects": self._top_subjects(),
            "folds": self.folds.summary(),
        }

    def dump(self, engine: object) -> None:
        """Never raises: a failed dump is one lost interval, never a lost
        run — the measurement may not cost the sheet it measures (review
        2026-09-17, blocking-1)."""
        try:
            self._dump(engine)
        except Exception as exc:
            print(f"sched-trace: dump failed ({exc!r})", file=sys.stderr,
                  flush=True)

    def _dump(self, engine: object) -> None:
        self._dumps += 1
        self._next_dump_s = self.wall_s() + self.every_s
        self.sample(engine, force=True)
        self._fires_fh.flush()
        self._timeline_fh.flush()
        self._ladder_fh.flush()
        self.folds.flush(None)
        _write_json(self.out_dir / "summary.json", self.summary(engine))
        _write_json(self.out_dir / "subscribers.json",
                    self._subscribers(engine))

    def finish(self, engine: object) -> None:
        try:
            self.dump(engine)
        finally:
            try:
                self.folds.close()
            except Exception:
                pass
            for handle in (self._fires_fh, self._timeline_fh,
                           self._ladder_fh):
                try:
                    handle.close()
                except Exception:
                    pass


def _two_key(counts: dict[tuple[str, str], int]) -> dict[str, Any]:
    out: dict[str, dict[str, int]] = {}
    for (outer, inner), value in counts.items():
        out.setdefault(outer, {})[inner] = value
    return {key: dict(sorted(row.items())) for key, row in sorted(out.items())}


def _fan_out_table(counts: dict[tuple[str, str], int]) -> dict[str, Any]:
    out: dict[str, dict[str, int]] = {}
    for (kind, plugin), value in counts.items():
        out.setdefault(kind, {})[plugin] = value
    return {kind: dict(sorted(row.items(), key=lambda item: -item[1]))
            for kind, row in sorted(out.items())}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomic: a killed run leaves the predecessor, never half a file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=False,
                              default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)


TRACE: NullTrace | SchedTrace = NullTrace()


def arm(run_dir: Path, workers: int = 1,
        every_s: float | None = None) -> SchedTrace:
    global TRACE
    trace = SchedTrace(
        Path(run_dir) / DIR_NAME,
        every_s=every_s_by_env() if every_s is None else every_s,
        workers=workers)
    TRACE = trace
    return trace


def disarm() -> None:
    global TRACE
    TRACE = NullTrace()

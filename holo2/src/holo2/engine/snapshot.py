"""What a run counts, and the frozen instant the observer is handed (L12).

Everything an observer can say about a run is counted here, once, by one
owner, and published as ONE frozen value minted on the MAIN thread. Both
halves of that sentence were defects before this module existed:

* **two owners, one name.** ``commits`` was tallied twice — the
  orchestrator's own counters and the observer's commit stream — and the
  two were bumped in the same breath with nothing enforcing agreement.
  They measurably disagreed (472 vs 471 on a bench run: the stream also
  counts what *ingest* commits before the queue exists), and the six-row
  block printed one owner's numerator over the other's denominator.
  :class:`CommitLedger` is now the only place a commit becomes a count,
  and it counts the run's own commits as a NAMED SUBSET of the total, so
  "total" and "scheduled" are two facts of one owner rather than two
  tallies of one word.
* **minted across threads.** ``snapshot()`` used to run on the HTTP
  thread: it iterated the scheduler's live dicts (``RuntimeError:
  dictionary changed size during iteration`` was reachable on any poll)
  and it called into the plane, whose derived views were then caches a
  committer owned — an observer that materialised them was writing state
  (engine/DESIGN.md, "unsynchronized observer snapshot"; the plane half
  of that hazard died with W-S wave 1, the scheduler half did not). The
  whole
  snapshot is now derived on the main thread at a commit boundary and
  PUSHED; the observer only ever reads a frozen value, and formats it on
  its own thread.

Staleness replaces the race, and is declared: a published snapshot is the
run as of the last commit, and a viewer asking for one is served the
previous instant while its request marks the next commit as wanted. That
is the honest trade — a fire is bounded but not instantaneous, so an
observer either lags a fire or races a committer, and only one of those
can corrupt a scheduler.

The engine may not name a solve or format type, so the plane's summaries
and the close family's report ride through as opaque JSON exactly as
they do everywhere else in this package: the mapping the plane composes
is the mapping the observer publishes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ..core import CommitResult, ResourceKey, WorkId


def _ratio(numerator: int, denominator: int) -> float:
    """A published rate, zero where nothing has happened yet."""
    return numerator / denominator if denominator else 0.0


# ------------------------------------------------------------- the ledgers

class CommitLedger:
    """Every commit of one session, counted once, by this object alone.

    The one method below is the ONLY place any of these numbers rises.
    ``scheduled`` names the run's own subset: the commits the queue
    caused, which is what a ``RunOutcome`` reports and what the wake
    ratio of the *fixpoint* (as opposed to the ratio of the whole
    session) is measured against.

    The two used to differ by the CAPTURES — assembly committed them
    before any queue existed, and the caller parked those commits here by
    hand. Since streaming ingestion (H4) an ingest is an ordinary
    scheduled fire, so a live run's two numbers coincide; the parking
    path stays, because a caller that commits outside a run (a repair, a
    driver, a test) is still entitled to be counted.

    Main-thread only, like every other write in the engine. The observer
    never reads it directly during a run: it reads the frozen
    :class:`CommitStream` this mints, published at a commit boundary.
    """

    def __init__(self) -> None:
        self.commits = 0
        self.changed_keys = 0
        self.wakes = 0
        self.scheduled_commits = 0
        self.scheduled_wakes = 0
        self.changed_by_kind: dict[str, int] = {}
        self.wakes_by_worker: dict[str, int] = {}

    def note(self, commit: CommitResult, *, scheduled: bool) -> None:
        """Count one commit. Every commit in a session passes here once."""
        self.commits += 1
        self.changed_keys += len(commit.changed_keys)
        self.wakes += len(commit.wakes)
        if scheduled:
            self.scheduled_commits += 1
            self.scheduled_wakes += len(commit.wakes)
        for key in commit.changed_keys:
            self.changed_by_kind[key.kind] = (
                self.changed_by_kind.get(key.kind, 0) + 1)
        for worker_id in commit.wakes:
            # Tallied by the DISPLAY rendering: a status page is JSON with
            # string keys, and a rendering collision costs one merged row
            # and no identity.
            rendered = str(worker_id)
            self.wakes_by_worker[rendered] = (
                self.wakes_by_worker.get(rendered, 0) + 1)

    def stream(self) -> "CommitStream":
        """The frozen instant. The dicts are copies: the observer keeps it."""
        return CommitStream(
            commits=self.commits,
            scheduled_commits=self.scheduled_commits,
            changed_keys=self.changed_keys,
            wakes=self.wakes,
            scheduled_wakes=self.scheduled_wakes,
            changed_by_kind=dict(sorted(self.changed_by_kind.items())),
            wakes_by_worker=dict(sorted(self.wakes_by_worker.items())),
        )


def subscription_kinds(subscriptions: Mapping[WorkId, tuple[ResourceKey, ...]],
                       sleeping: Iterable[WorkId]) -> dict[str, int]:
    """Which KINDS of key the idle workers are waiting on (the §7 surface).

    The observer's one honest question about a quiet queue: not who is
    asleep, but what they are asleep ON. It lives here beside the views
    it feeds, because it is a rendering of durable state and not a
    decision.
    """
    counts: dict[str, int] = {}
    for worker_id in sleeping:
        for key in subscriptions.get(worker_id, ()):
            counts[key.kind] = counts.get(key.kind, 0) + 1
    return dict(sorted(counts.items()))


class WorkLedger:
    """What the queue did, counted once, by this object alone.

    The commit numbers are deliberately absent: they belong to
    :class:`CommitLedger`, which counts ingest's commits too, and a second
    tally of the same word is the defect this module exists to end.
    :meth:`counters` takes them from that one owner.
    """

    def __init__(self) -> None:
        self.fires = 0
        self.idle_pops = 0
        self.useful_fires = 0
        self.consults = 0
        self.observations = 0
        self.work_units = 0
        self.peak_inflight = 0
        self.dispatched = 0
        self.stale_discards = 0
        self.cancelled = 0
        self.fires_by_worker: dict[str, int] = {}
        self.outcomes: dict[str, int] = {}

    def counters(self, commits: CommitLedger) -> "WorkCounters":
        """The frozen instant, with the scheduled commit facts folded in."""
        return WorkCounters(
            commits=commits.scheduled_commits,
            wakes=commits.scheduled_wakes,
            fires=self.fires,
            idle_pops=self.idle_pops,
            useful_fires=self.useful_fires,
            consults=self.consults,
            observations=self.observations,
            work_units=self.work_units,
            peak_inflight=self.peak_inflight,
            dispatched=self.dispatched,
            stale_discards=self.stale_discards,
            cancelled=self.cancelled,
            fires_by_worker=dict(sorted(self.fires_by_worker.items())),
            outcomes=dict(sorted(self.outcomes.items())),
        )


# -------------------------------------------------------- the frozen views

@dataclass(frozen=True)
class CommitStream:
    """Every commit of the session, and the run's own subset of them."""

    commits: int = 0
    scheduled_commits: int = 0
    changed_keys: int = 0
    wakes: int = 0
    scheduled_wakes: int = 0
    changed_by_kind: Mapping[str, int] = field(default_factory=dict)
    wakes_by_worker: Mapping[str, int] = field(default_factory=dict)

    @property
    def wakes_per_commit(self) -> float:
        """Wakes over commits — one owner's numerator over its own count."""
        return _ratio(self.wakes, self.commits)

    def to_json(self) -> dict[str, Any]:
        return {
            "commits": self.commits,
            "scheduled_commits": self.scheduled_commits,
            "changed_keys": self.changed_keys,
            "wakes": self.wakes,
            "scheduled_wakes": self.scheduled_wakes,
            "wakes_per_commit": self.wakes_per_commit,
            "changed_by_kind": dict(self.changed_by_kind),
            "wakes_by_worker": dict(self.wakes_by_worker),
        }


@dataclass(frozen=True)
class WorkCounters:
    """The fixpoint's own numbers: what the queue fired, spent and woke."""

    commits: int = 0                  # the run's subset of the stream
    wakes: int = 0                    # ditto, so the ratio below matches
    fires: int = 0
    idle_pops: int = 0
    useful_fires: int = 0
    consults: int = 0                 # deciding looks (mode close/final)
    observations: int = 0             # counting looks (mode observe)
    work_units: int = 0
    #: The widest the pool ever actually ran: the most fires in flight at
    #: once. Zero on the serial path, which builds no pool — it replaced
    #: ``rounds``/``mean_round_width`` when continuous admission dissolved
    #: the round (W-S, R9).
    peak_inflight: int = 0
    dispatched: int = 0               # fires handed to the pool
    stale_discards: int = 0
    cancelled: int = 0                # fires dropped by close preemption
    fires_by_worker: Mapping[str, int] = field(default_factory=dict)
    outcomes: Mapping[str, int] = field(default_factory=dict)

    @property
    def stale_discard_ratio(self) -> float:
        return _ratio(self.stale_discards, self.dispatched)

    @property
    def wakes_per_commit(self) -> float:
        return _ratio(self.wakes, self.commits)

    @property
    def useful_rerun_ratio(self) -> float:
        return _ratio(self.useful_fires, self.fires)

    def to_json(self) -> dict[str, Any]:
        return {
            "commits": self.commits,
            "fires": self.fires,
            "idle_pops": self.idle_pops,
            "wakes": self.wakes,
            "consults": self.consults,
            "observations": self.observations,
            "work_units": self.work_units,
            "peak_inflight": self.peak_inflight,
            "dispatched": self.dispatched,
            "stale_discards": self.stale_discards,
            "cancelled": self.cancelled,
            "stale_discard_ratio": self.stale_discard_ratio,
            "wakes_per_commit": self.wakes_per_commit,
            "useful_rerun_ratio": self.useful_rerun_ratio,
            "outcomes": dict(self.outcomes),
        }


@dataclass(frozen=True)
class QueueView:
    """The ready queue: how deep, and of what."""

    depth: int = 0
    by_family: Mapping[str, int] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"depth": self.depth, "by_family": dict(self.by_family)}


@dataclass(frozen=True)
class WorkerView:
    """The worker population at one instant, by lifecycle stage."""

    total: int = 0
    running: tuple[str, ...] = ()
    sleeping: int = 0
    retired: int = 0
    # A permanent decline is out of the domain for good; a pending one is
    # a descriptor asleep on its own wake keys.
    declined: int = 0
    declined_pending: int = 0
    declined_by_reason: Mapping[str, int] = field(default_factory=dict)
    fires_by_worker: Mapping[str, int] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "running": list(self.running),
            "sleeping": self.sleeping,
            "retired": self.retired,
            "declined": self.declined,
            "declined_pending": self.declined_pending,
            "declined_by_reason": dict(self.declined_by_reason),
            "fires_by_worker": dict(self.fires_by_worker),
        }


@dataclass(frozen=True)
class RunSnapshot:
    """One instant of a run: the whole observer story, frozen.

    ``plane`` and ``close`` are the two opaque passengers: a tile map, a
    done projection, a counted CRC exposure and a fountain state are
    other packages' vocabulary, and the engine relays their JSON without
    typing it (the same rule that keeps ``RunOutcome.close`` a dict). The
    plane's keys are spread into the session mapping under the plane's
    OWN names, and the engine's keys are written after them, so a plane
    can add a summary without a change here and cannot shadow a
    scheduler fact.
    """

    recipe: str = ""
    complete: bool = False
    mode: str = "free"
    pool_size: int = 1
    providers: tuple[str, ...] = ()
    queue: QueueView = field(default_factory=QueueView)
    workers: WorkerView = field(default_factory=WorkerView)
    counters: WorkCounters = field(default_factory=WorkCounters)
    stream: CommitStream = field(default_factory=CommitStream)
    leases: Mapping[str, int] = field(default_factory=dict)
    sleeping_by_subscription_key: Mapping[str, int] = field(
        default_factory=dict)
    plane: Mapping[str, object] = field(default_factory=dict)
    close: Mapping[str, object] = field(default_factory=dict)

    def session_json(self) -> dict[str, Any]:
        """The scheduler half, under the key names the surface publishes."""
        session: dict[str, Any] = dict(self.plane)
        session.update({
            "recipe": self.recipe,
            "complete": self.complete,
            "mode": self.mode,
            "pool_size": self.pool_size,
            "providers": list(self.providers),
            "ready": self.queue.to_json(),
            "workers": self.workers.to_json(),
            "leases": dict(self.leases),
            "sleeping_by_subscription_key": dict(
                self.sleeping_by_subscription_key),
            "counters": self.counters.to_json(),
            "close": dict(self.close),
        })
        return session

    def to_json(self) -> dict[str, Any]:
        """The ONE wire mapping: both halves of the status, one instant."""
        return {"commit_stream": self.stream.to_json(),
                "session": self.session_json()}


__all__ = ["CommitLedger", "CommitStream", "QueueView", "RunSnapshot",
           "WorkCounters", "WorkLedger", "WorkerView", "subscription_kinds"]
